
## import (add more if you need)
from pickle import NONE
from struct import pack
from time import sleep 
import threading
import unreliable_channel
import socket
import sys
import zlib

## define and initialize
packets = [] #list of all packets that need to be sent
window = [] #list of tuples of current packets in the window and their status 
packets_sent = [] #list of the packet seq nums that have been sent
window_size = int(sys.argv[3]) 
ip = sys.argv[1] #ip argument
port = sys.argv[2]
oldest = 0 #the seq num of the oldest unacked packet
window_current = 0 #current number of packets in the window
next_seq_number = 0 #default value
ptype = format(0, '#010x') #packet type, 0 for DATA, 1 for ACK, represented in 4 byte hex (0x00000001)
dup_ack_count = 1 #how many dup acks have been received so far
packet_index = 0 #keep track of what packet is being sent
window_lock = threading.Lock() #lock for synchronizing the use of sending from the window and updating it 
dup_ack_number = 0 #keep track of the dup ack seq num that needs to be resent 
sender_finished = False #to let the other thread know that the senders is done
packet_lengths = [] #contains the length of all the packets 
packet_checksums = [] #conatins the checksum of all the packets  
log_file = open(sys.argv[5], 'a') #opening the log file for logging
print_window_lock = True  #used to control when the status of the window is logged so that it doesnt log unncessarily 
temp_timer = None #this is the timer variable that will be used for our temporary timers for each oldest packet sent 
oldest_changed = True  #this is used to control the timer and when its created based on the oldest packet

# open client socket and bind
sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sender_socket.bind(("127.0.0.1", 64198)) #binded to my local port 64198

## we will need a lock to protect against concurrent threads
lock = threading.Lock()

def timeout():
	global sender_socket
	global log_file
	global temp_timer

	unreliable_channel.send_packet(sender_socket, bytes.fromhex(oldest[0]), (ip, int(port)))
	log_file.write("Timeout for packet seqNum=" + str(oldest[1]) + "\nRetransmitted pkt; type=DATA; seqNum=" + str(oldest[1]) + ";\nlength=" + str(packet_lengths[oldest[1]]) + "; checksum=" + str(packet_checksums[oldest[1]]) + "\n\n")

def create_packet(data):
	global packet_lengths
	global packet_checksums
	global next_seq_number
	packet = "" #finalized packet in hex format
	dataHex = "" #what the data will be in hex format
	tempPacket = "" #only for calculating checksum

	length = 16 + len(data) #length of the data
	packet += ptype + format(next_seq_number, '#010x') + format(length, '#010x') #add first 3 fields of header in hex format
	tempPacket = packet + data #adding the string data to the first 3 fields in order to calculate the checksum 
	checksum = zlib.crc32(tempPacket.encode()) #get the checksum
	packet += format(checksum, '#010x') #add checksum to packet
	for c in data: 
		dataHex += format(ord(c), '#04x')  #Concatenates the hex value of each character to form data in hex format
	
	packet_lengths.append(length) 
	packet_checksums.append(checksum) 

	packet += dataHex #add the data hex to the packet last to maintain order, type -> seqNum -> length -> checksum -> data
	packet = packet.replace('0x', '') #get rid of all the "0x" 
	packets.append(packet) #adds packet to packets list
	next_seq_number = next_seq_number + 1 #update next seq number accordingly

def extract_packet_info(packet):
	hexData = "" #packet data in hex string
	temp = []

	for i in packet:
		hexData += format(i, '#04x')
	
	hexData = hexData.replace('0x', '')

	ptype = int(hexData[0:8],16)
	seqNum = int(hexData[8:16],16)
	length = int(hexData[16:24],16)
	checksum = int(hexData[24:],16)

	temp.append(ptype)
	temp.append(seqNum)
	temp.append(length)
	temp.append(checksum)

	return temp

#Checks to see if anything is wrong with the packet, duplicate (1) or corrupt (2), or none (0)
def packet_check(packet_info):
	global dup_ack_number
	global temp_timer
	sender_checksum = format(packet_info[0], '#010x') + format(packet_info[1], '#010x') + format(packet_info[2], '#010x')
	sender_checksum = zlib.crc32(sender_checksum.encode())

	if (dup_ack_number == packet_info[1]): #DUP ack since the dup_ack_number is the same as the packet seq num
		return 1

	dup_ack_number = packet_info[1] #will change if the packet seq num is not the same as the last ack num received (dup_ack_number)

	if (packet_info[3] != sender_checksum): #checksum does not match, corrupt packet
		return 2
	else: #packet that was received has the expected seq number and is not corrupt
		temp_timer.cancel() #cancel the timer for old ack immediately 
		return 0

#Updates the window and the status of the packets based on the seqNum of the ACK that was sent
def update_window(seqNum): 
	global log_file
	global print_window_lock
	global oldest_changed 
	remove = [] #contains the packets that need to be removed 

	window_lock.acquire() #if the window is currently being used or packets are being sent, dont continue

	for p in window: 
		if (p[1] < seqNum): #if the seqNum in the ACK packet is greater than the seqNum in the window, then it has ACKED the prior packets 
			p[2] = 1 #change its status to 1 for ACKED
			remove.append(p)
	
	#print the window before updating it
	log_file.write("Updating window; (0: sent but not acked, 1: acked)\n")
	log_file.write(print_window_state()) 
	#print(seqNum) 

	#update the window by removing the ACKED packets 
	for p in remove: 
		if (p[1] < seqNum): 
			window.remove(p) #remove the packet from the window

	print_window_lock = True #reset since the window has been updated
	oldest_changed = True #the oldest packet in the window is different now since the window changed
	window_lock.release() #release so the main thread can send more packets

def print_window_state(): 
	windowState = "Window State: [ "
	for p in window: 
		windowState += str(p[1]) + "(" + str(p[2]) + ") "
	windowState += "]\n\n"
	return windowState

#Will be receiving ACKS , update timer 
def receive_thread(sender_socket):
	global dup_ack_count
	global log_file
	while True:
		try:
			if (sender_finished == True): 
				break
			ACK_packet = unreliable_channel.recv_packet(sender_socket) #ACK_packet = sender_socket.recvfrom(1472)
			temp = extract_packet_info(ACK_packet[0])
			pc = packet_check(temp)
			if (pc == 0): #packet was not corrupt or a duplicate
				update_window(temp[1]) #send the ACK packet's seqNum to update window
			elif (pc == 1): #DUP ACK
				dup_ack_count += 1 #increment dup ack count
			elif (pc == 2): #corrupt packet
				log_file.write("Corrupt ACK received, ignoring\n\n")
		except: 
			sys.exit(0)

def main(input):
	global packet_index
	global oldest 
	global window_size
	global dup_ack_count
	global dup_ack_number
	global sender_finished
	global packet_lengths
	global packet_checksums
	global log_file
	global print_window_lock
	global sender_socket  
	global temp_timer
	global oldest_changed 
	
	# open input file
	data_file = open(input, 'r')

	# start receive thread
	recv_thread = threading.Thread(target=receive_thread,args=(sender_socket,))
	recv_thread.start()

	log_file.write("Making packets for file " + input + "\n\n") 
	# take the input file and split it into packets (use create_packet)
	byteCount = 0 #keeps track of how many bytes have been read
	data = "" #the packet data 
	while (byteCount < 1456): #1456 is the most data bytes that can fit in a packet
		byte = data_file.read(1) #one char/byte of data
		if (byteCount == 1455):
			data += byte
			create_packet(data)
			data = "" #reset for next packet
			byteCount = 0 #reset for next packet
		elif not byte: #no more characters left
			if (len(data) != 0): #there is some data
				create_packet(data)
			break
		else:
			data += byte 
			byteCount += 1

	data_file.close()

	#Sending PACKETS
	while True: #while there are packets to send
		window_lock.acquire() #if the window is being updated, dont continue 
		if (packet_index >= len(packets) and len(window) == 0): #if there are no more packets to send and the window is empty(all packets were ACKED) break out of the loop
			break 
		if (dup_ack_count >= 3): #trip dup handling
			try: 
				unreliable_channel.send_packet(sender_socket, bytes.fromhex(packets[dup_ack_number]), (ip, int(port)))
				dup_ack_count = 0 #reset 
				if (dup_ack_number >= len(packets)): #make sure to not get index out of bounds
					break
				log_file.write("Triple dup acks received for packet seqNum=" + str(dup_ack_number) + "\n")
				log_file.write("Retransmitted pkt; type=DATA; seqNum=" + str(dup_ack_number) + "\nlength=" + str(packet_lengths[dup_ack_number]) + "; checksum=" + str(packet_checksums[dup_ack_number]) + "\n\n")
				window_lock.release()
				continue
			except: 
				print("list index out of bounds becaues of dup ack number: " + str(dup_ack_number))
				sys.exit(0)
		while (len(window) != window_size): #available space in the window so send packets 
			if (packet_index >= len(packets)): #make sure to not get index out of bounds 
				oldest = window[0]
				break 
			window.append([packets[packet_index], packet_index, 0]) #append list: [packet, packetSeqNum, status] to the window  
			oldest = window[0] #the oldest packet in the window is the first element in the list
			unreliable_channel.send_packet(sender_socket, bytes.fromhex(packets[packet_index]), (ip, int(port))) #send the packet
			log_file.write("Packet sent; type=DATA; seqNum=" + str(packet_index) + ";\nlength=" + str(packet_lengths[packet_index]) + ";checksum=" + str(packet_checksums[packet_index]) + ";\n\n")
			if (oldest_changed == True): #if the oldest packet is different, start a timer 
				if (temp_timer != None and temp_timer.is_alive()): #if there is another timer that is alive, then stop it
					temp_timer.cancel()  
				temp_timer = threading.Timer(0.5, timeout) 
				temp_timer.start() 
				oldest_changed = False #set to False so that the timer is not changed on every loop 
			packet_index += 1 #update packet index
		if (print_window_lock == True): #can log the status of the window, makes sure it is not logging on every rotation 
			log_file.write("Window full, waiting for acks\n")
			log_file.write(print_window_state())
			print_window_lock = False 
		window_lock.release()

	if (temp_timer.is_alive()):
		temp_timer.cancel() 
	sleep(3) #sleep for 3 sec to make sure the last packet is ACKED
	create_packet("") 
	sender_socket.sendto(bytes.fromhex(packets[-1]), (ip, int(port))) #sending the "empty" packet
	sender_socket.close() 
	log_file.close() 
	print("SENDER FINSIHED")
	sender_finished = True 
	recv_thread.join() 

if __name__ == "__main__":
    main(sys.argv[4])


