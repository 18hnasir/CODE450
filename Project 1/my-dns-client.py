import socket
import sys

#print("\033c")

def mydnsclient(hostname):
    finalQuery = ""
    udpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udpSocket.settimeout(5) #5 second timeout set for receiving response
    attempt = 1 #keep track of the sending attempts
    
    #Header Section
    ID = hex(43420) #kept same for all requests
    #FLAGS is the hex value of the second row in the header section
    #QR OPCODE AA TC RD RA  Z  RCODE
    #0  0000   0  0  1  0  000 0000
    FLAGS = "0100" 
    QDCOUNT, ANCOUNT, NSCOUNT, ARCOUNT = "0001", "0000", "0000", "0000"

    #Question Section
    QNAME = ""
    QTYPE = "0001" #A type
    QCLASS = "0001" #Internet
    
    #Constructing the QNAME
    hostnameSplit = hostname.split('.') #splits the hostname into labels ex. ["gmu", "edu"]
    for i in hostnameSplit: 
        QNAME += format(len(i), '#04x') #Concatenates the length of the current label
        for k in i: 
            QNAME += format(ord(k), '#04x')  #Concatenates the hex value of each label character
    QNAME += format(0, '#04x') #Concatenates a 0 for the null label of the root
    
    #Putting the query together
    headerQuery = ID + FLAGS + QDCOUNT + ANCOUNT + NSCOUNT + ARCOUNT
    questionQuery = QNAME + QTYPE + QCLASS
    finalQuery = headerQuery + questionQuery
    finalQuery = finalQuery.replace('0x', '')

    #Printing info to user
    print("Preparing DNS Query") 
    print("DNS query header = " + headerQuery.replace('0x', ''))
    print("DNS query question section = " + questionQuery.replace('0x', ''))
    print("Complete DNS Query = " + finalQuery + "\n")

    #Making query into hex and then sending and receiving data
    print("Contacting DNS server..")
    print("Sending DNS query..")
    hexQuery = bytes.fromhex(finalQuery)
    while(attempt < 4):
        print("DNS response received (attempt " + str(attempt) + " of 3)")
        try:
            udpSocket.sendto(hexQuery, ("8.8.8.8", 53))
            data = udpSocket.recvfrom(2048)
            print("Processing DNS response..")
            print("------------------------------------------------------------")
            break
        except: #if timer runs out, then redo 
            attempt += 1
            if (attempt == 4):
                print("ERROR, NO RESPONSE RECEIVED")
                return None
            continue
    
    udpSocket.close()
    hexData = ""

    #Turning the data into a string hex
    for i in data[0]:
        hexData += format(i, '#04x') 
    
    #Getting rid of the 0x prefix and the first 4 hex values in the string
    hexData = hexData.replace('0x', '')
    hexData = hexData[4:]

    #Get the second row values in the header in decimal
    FLAGS = extractFlags(hexData[0:4])
    #Get the rest of the header values
    QDCOUNT = hexData[4:8]
    ANCOUNT = hexData[8:12]
    NSCOUNT = hexData[12:16]
    ARCOUNT = hexData[16:20]

    answerStartIndex = 28 + len(QNAME.replace('0x', '')) #the index of where the answer section starts

    #Cutting down hex string to only the answer portion
    hexData = hexData[answerStartIndex:]

    #Print the output information to user
    printHeader(FLAGS, QDCOUNT, ANCOUNT, NSCOUNT, ARCOUNT)
    printQuestion(hostname)
    while(hexData != ""):
        temp = extractRR(hexData)
        printRR(temp)
        hexData = hexData[temp[6]:]

#Function prints DNS header information
def printHeader(data, QDCOUNT, ANCOUNT, NSCOUNT, ARCOUNT):
    print("\n")
    print("header.ID      = a99c")
    print("header.QR      = " +  data[0])
    print("header.OPCODE  = " +  data[1])
    print("header.AA      = 0000")
    print("header.TC      = " +  data[3])
    print("header.RD      = " +  data[4])
    print("header.RA      = " +  data[5])
    print("header.Z       = " +  data[6])
    print("header.RCODE   = " +  data[7])
    print("header.QDCOUNT = " + QDCOUNT)
    print("header.ANCOUNT = " + ANCOUNT)
    print("header.NSCOUNT = " + NSCOUNT)
    print("header.ARCOUNT = " + ARCOUNT)
    print("\n")

#Function print DNS question information
def printQuestion(QNAME): 
    print("question.QNAME  = " + QNAME)
    print("question.QTYPE  = 0001")
    print("question.QCLASS = 0001")
    print("\n")

#Function prints RR or answer information
def printRR(data):
    print("answer.NAME     = " + data[0])
    print("answer.TYPE     = " + data[1])
    print("answer.CLASS    = " + data[2])
    print("answer.TTL      = " + data[3])
    print("answer.RDLENGTH = " + data[4])
    print("answer.RDATA    = " + toIP(data[5]))
    print("\n")

#Function returns list of the second row values in hex of the DNS header
def extractFlags(hexData):
    values = [] #QR, OPCODE, AA, TC, RD, RA, Z, RCODE
    binary = bin(int(hexData, 16))[2:] #converts hex to binary


    #converts binary to decimal to hexadecimal length 4 format
    QR = format(int(binary[0], 2), '#06x').replace('0x', '')
    OPCODE = format(int(binary[1:5], 2), '#06x').replace('0x', '')
    AA = format(int(binary[5], 2), '#06x').replace('0x', '')
    TC = format(int(binary[6], 2), '#06x').replace('0x', '')
    RD = format(int(binary[7], 2), '#06x').replace('0x', '')
    RA = format(int(binary[8], 2), '#06x').replace('0x', '')
    Z = format(int(binary[9:12], 2), '#06x').replace('0x', '')
    RCODE = format(int(binary[12:], 2), '#06x').replace('0x', '')

    #Appending all the value in the list
    values.append(QR)
    values.append(OPCODE)
    values.append(AA)
    values.append(TC)
    values.append(RD)
    values.append(RA)
    values.append(Z)
    values.append(RCODE)

    return values

#Function returns list of answer values for a given portion
#and returns the start of the next answer portion
def extractRR(hexData):
    values = []
    cutoff = 32 #normal cutoff for type A

    NAME = hexData[0:4]
    TYPE = hexData[4:8]
    CLASS = hexData[8:12]
    TTL = hexData[12:20]
    DL = hexData[20:24]

    if (int(hexData[4:8]) == 5): #if the first answer is a CNAME
        cutoff = 24 + (2 * int(DL, 16)) #cutoff for type CNAME
        ADDY = hexData[24:cutoff]
    else: 
        ADDY = hexData[24:32]

    values.append(NAME)
    values.append(TYPE)
    values.append(CLASS)
    values.append(TTL)
    values.append(DL)
    values.append(ADDY)
    values.append(cutoff) #to know what next answer index to start at

    return values

#Function converts hex to an IP address
def toIP(hexData):
    seperated = [] #keeps the hex values
    IP = "" 

    #If its a CNAME, then just return the hex
    if(len(hexData) != 8):
        return hexData

    #Adds each section of the IP in hex to list
    while(hexData != ""):
        seperated.append(hexData[0:2])
        hexData = hexData[2:]

    #Converts the hex value to decimal and forms IP 
    for i in seperated:
        IP += str(int(i, 16)) + "."

    IP = IP[:-1] #remove last '.'

    return IP

if __name__ == "__main__":
    mydnsclient(sys.argv[1])




