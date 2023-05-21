To compile the program, first have both the MTPSender.py and MTPReceiver.py python files in the same directory along with 
the file that needs to be transferred, for example "1MB.txt" 

Then open up two terminals, one for executing MTPReceiver.py and the other for executing MTPSender.py, make sure to execute
MTPReceiver.py first then MTPSender.py

For MTPReceiver.py, I had the following arguments/command: "python MTPReceiver.py 5000 output.txt rlog.txt" 

For MTPSender.py, I had the following arguments/command: "python MTPSender.py 127.0.0.1 5000 25 1MB.txt slog.txt" 


NOTE: I decided to go with the port 5000 for binding my receiver socket in MTPReceiver, and I also used the local IP address of 
127.0.0.1 for both my MTPSender and MTPReceiver. ALSO, for my program to work, I had to bind my sender_socket to my local port 
64198 (MTPSender.py, line 37) in order for my program to run, otherwise it was giving me an OS Window error, you may have 
to change this port to your local port possibly or the port that the receiver gets in the address variable in 
MTPReceiver.py, line 113 in order to run the program. 