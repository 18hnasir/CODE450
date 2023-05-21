
## imports (add more if you need)
from time import sleep
import unreliable_channel
import threading 
import socket
import sys
import zlib

ptype = format(1, '#010x') #packet type, 0 for DATA, 1 for ACK, represented in 4 byte hex (0x00000000)
expected_seq_number = 0 #what the receiver expects to receive
received_buffer = [] #buffer list that contains received packets
out_of_order = [] #list containing the seq numbers of the out of order packets
data_ooo = [] #contain all the data that has been out of order
awaiting = False #keep track of if another in order segment has an ACK Pending 
address = None
receiver_finished = False #to let thread know the receiver is finished 
receive_checksum = None #checksum calculated at the receiver side 
sent_checksum = None #checksum calculated for the ACK packet being sent 
temp_timer = None #timer for receiving packets 
packet_came = True #used to see if a new packet came in
send = False #used to see if only a regular ack should be sent

#No other packet came in within  500ms, so just send a regular ACK 
def send_ack(): 
	global send
	send = True 

def create_packet(seqNum): 
	global sent_checksum
	packet = "" #finalized packet in hex format
	length = format(16, '#010x') #length is 16 since no data in ACK packet

	packet += ptype + format(seqNum, '#010x') + length #add first 3 fields of header in hex format
	checksum = zlib.crc32(packet.encode()) #get the checksum
	sent_checksum = checksum 
	packet += format(checksum, '#010x') #add checksum to packet

	packet = packet.replace('0x', '') #get rid of all the "0x" 

	return packet

def extract_packet_info(packet): 
	hexData = "" #packet data in hex string
	index = 0 #keep track of where to stop for the header portion
	temp = []

	for i in packet:
		if (index == 16):
			break
		hexData += format(i, '#04x')
		index += 1
	
	hexData = hexData.replace('0x', '')

	ptype = int(hexData[0:8],16)
	seqNum = int(hexData[8:16],16)
	length = int(hexData[16:24],16)
	checksum = int(hexData[24:32],16)
	message = packet[16:].decode()  

	temp.append(ptype)
	temp.append(seqNum)
	temp.append(length)
	temp.append(checksum)
	temp.append(message)

	return temp

#Checks to see if anything is wrong with the packet, out of order (1) or corrupt (2), or none (0)
def packet_check(packet_info):
	global expected_seq_number
	global receive_checksum
	receiver_checksum = format(packet_info[0], '#010x') + format(packet_info[1], '#010x') + format(packet_info[2], '#010x') + packet_info[4]
	receiver_checksum = zlib.crc32(receiver_checksum.encode())
	receive_checksum = receiver_checksum

	if (packet_info[2] == 16): #empty packet
		return -1 
	if (packet_info[3] != receiver_checksum): #checksum does not match, corrupt packet
		return 2	
	if (packet_info[1] < expected_seq_number): #premature timeout so just send what the receiver expects again 
		return 3 
	if (packet_info[1] != expected_seq_number): #packet is out of order since it is greater than the expected sequence num 
		return 1
	else: #packet that was received has the expected seq number and is not corrupt
		return 0

def out_order():
	global out_of_order
	temp = None

	if (len(out_of_order) != 0): #there were out of order packets
					temp = out_of_order[-1] #get the seq num of the last out of order packet
					out_of_order.clear() #reset the list
	
	return temp 

#Will be receiving DATA
def receive_thread(receiver_socket):
	global address
	global temp_timer
	global awaiting 
	global received_buffer
	global expected_seq_number

	while True:
		try:
			if (receiver_finished == True):
				break
			bytesAddressPair = unreliable_channel.recv_packet(receiver_socket)
			DATA_packet = bytesAddressPair[0] #DATA Packet
			address = bytesAddressPair[1] #address
			received_buffer.append(DATA_packet) #store in buffer
			if (temp_timer != None and temp_timer.is_alive()): #Another packet came in while the timer was still active so we have to send a cumalative ACK 
				temp_timer.cancel() 
				awaiting = True
			else: #start a timer to see if another comes in 
				temp_timer = threading.Timer(0.5, send_ack) 
				temp_timer.start() 
		except: 
			sys.exit(0)
		

def main(port, output, rlog):
	global expected_seq_number
	global address
	global receiver_finished
	global awaiting
	global out_of_order
	global receive_checksum
	global sent_checksum
	global receiver_socket
	global send 
	data_ooo = []  #contain all the data that has been out of order 

	#opening output.txt and going to write the date to this file and opening log file for logging 
	output_file = open(output, 'a')
	log_file = open(rlog, 'a') 

	# open server socket and bind
	receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	receiver_socket.bind(("127.0.0.1", int(port)))

	# start receive thread
	recv_thread = threading.Thread(target=receive_thread,args=(receiver_socket,))
	recv_thread.start()

	while True:
		if (len(received_buffer) != 0): #there are packets in the buffer
			temp = extract_packet_info(received_buffer[0])
			pc = packet_check(temp) #do a packet check on the received packet
			if (pc == -1): #empty packet so receiver can stop
				break
			if (pc == 0): #if not corrupt and in order
				expected_seq_number += 1 #update 
				output_file.write(temp[4]) #write the data to the file
				for d in data_ooo: #write all the out of order packet data as well if there is any 
					output_file.write(d)
				data_ooo.clear() #clear it 
				if (awaiting == True): #Another segment has ACK Pending, so send cumalative ACK for both in order packets
					received_buffer.pop(0)
					out = out_order()
					if (out != None): 
						expected_seq_number = out + 1 #EX. if 3 was the last out of order packet, then the new expected would be 4 
					ACK_packet = create_packet(expected_seq_number)
					unreliable_channel.send_packet(receiver_socket, bytes.fromhex(ACK_packet), address) 
					awaiting = False #reset 
					log_file.write("Packet sent; type=ACK; seqNum=" + str(expected_seq_number) + "; length=16;\nchecksum_in_packet=" + str(sent_checksum) + ";\n\n")
				else: #no other packet came in after 500 ms so send regualr ack 
					received_buffer.pop(0) 
					out = out_order()
					if (out != None): 
						expected_seq_number = out + 1 #EX. if 3 was the last out of order packet, then the new expected would be 4 
					ACK_packet = create_packet(expected_seq_number)
					unreliable_channel.send_packet(receiver_socket, bytes.fromhex(ACK_packet), address) 
					log_file.write("Packet Received, type=DATA; seqNum=" + str(temp[1]) + ";\n length=" + str(temp[2]) + "; checksum_in_packet=" + str(temp[3]) + ";\n checksum_calculated=" + str(receive_checksum) + "; status=NOT_CORRUPT\n\n")
					log_file.write("Packet sent; type=ACK; seqNum=" + str(expected_seq_number) + "; length=16;\nchecksum_in_packet=" + str(sent_checksum) + ";\n\n") 
					send = False
			else: 
				if (pc == 1): #out of order
					data_ooo.append(temp[4])
					out_of_order.append(temp[1]) #append the seqNum of the out of order packet
					log_file.write("Packet Received, type=DATA; seqNum=" + str(temp[1]) + ";\n length=" + str(temp[2]) + "; checksum_in_packet=" + str(temp[3]) + ";\n checksum_calculated=" + str(receive_checksum) + "; status=OUT_OF_ORDER_PACKET\n\n")
				if (pc == 2): #corrupt packet
					log_file.write("Packet Received, type=DATA; seqNum=" + str(temp[1]) + ";\n length=" + str(temp[2]) + "; checksum_in_packet=" + str(temp[3]) + ";\n checksum_calculated=" + str(receive_checksum) + "; status=CORRUPT_PACKET\n\n")
				ACK_packet = create_packet(expected_seq_number) #send dup ACK of what it expected to receive
				unreliable_channel.send_packet(receiver_socket, bytes.fromhex(ACK_packet), address)
				log_file.write("Packet sent; type=ACK; seqNum=" + str(expected_seq_number) + "; length=16;\nchecksum_in_packet=" + str(sent_checksum) + ";\n\n")
				received_buffer.pop(0)

	receiver_socket.close() 
	receiver_finished = True 
	output_file.close()
	log_file.close() 
	print("RECEIVER FINISHED")
	recv_thread.join() 

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
