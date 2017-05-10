#!/usr/bin/env python

import sys
import socket

#from struct import pack
import struct
import time

sync_header_bytes = (0xDC,0xC0,0x23,0xC2,0xDC,0xC0,0x23,0xC2)

SYNC_LENGTH = len(sync_header_bytes)

SYNC = 0xDCC023C2

PACKET_SIZE = 1024

PASSIVE = 0
ACTIVE = 1

MAXTIMEOUT = 1

def _carry_around_add(a, b):
    c = a + b
    return (c & 0xffff) + (c >> 16)

def checksum(msg):
    s = 0
    if len(msg) % 2 == 1:
            msg += "\0"
    for i in range(0, len(msg),2):
        w = (ord(msg[i]) << 8) + (ord(msg[i+1]))
        s = _carry_around_add(s, w)
    return (~s) & 0xffff



class Emulator(object):

    def __init__(self, conn_type, host, port, input_file, output_file):
        self.base_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.base_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.host = host
        self.port = port
        self.input_file = input_file
        self.output_file = output_file

        if conn_type == ACTIVE:
            self.sock = self._open_active()
        elif conn_type == PASSIVE:
            self.sock = self._open_passive()

    def start(self):
        main(self.input_file, self.output_file, self.sock)

    def _open_active(self):
        self.base_sock.connect((self.host, self.port))
        return self.base_sock

    def _open_passive(self):
        self.base_sock.bind((self.host, self.port))
        self.base_sock.listen(1)
        conn, address = self.base_sock.accept()
        return conn



def build_frame(frame_id, data = [], ack = False, end = False):
    #header
    flags = 0
    if ack:
        flags |= 0x80

    if end:
        flags |= 0x40

    length = len(data)

    header = struct.pack('!IIHHH', SYNC, SYNC, 0, length, (frame_id<<8)|(flags))

    data = struct.pack("!%dB" % len(data), *data)

    frame_str = header+data

    chcksum = checksum(frame_str)

    frame = bytearray(frame_str)
    frame[8] = chcksum >> 8
    frame[9] = chcksum & 0xff
    frame_str = str(frame)

    return frame_str



def decode_header(syncless_header):
    chksum,length,frame_id, flags = struct.unpack('!HHBB',syncless_header)
    ack = bool(flags & 0x80)
    end = bool(flags & 0x40)
    return chksum, length, frame_id, ack, end


def get_timeout(start_time):
    current_time = time.time()
    timedelta = current_time - start_time

    return MAXTIMEOUT - (0 if timedelta >= MAXTIMEOUT else timedelta)



def recv_valid_synced_frame(sock, resend_frame = '', start_time = 0):
    last_sync = 0
    current_sync = 0
    current_sync_unpacked = 0
    last_sync_unpacked = 0

    while True:
        if resend_frame:
            sock.settimeout(get_timeout(start_time))
        else:
            sock.settimeout(None)

        try:
            # while current_sync_unpacked != SYNC or last_sync_unpacked != SYNC:
            #     last_sync = current_sync
            #     last_sync_unpacked = current_sync_unpacked
            #     current_sync = sock.recv(4)
            #     current_sync_unpacked = struct.unpack('!I',current_sync)[0]
            i = 0
            sync_header = ''
            while(i < SYNC_LENGTH):
                current_byte = sock.recv(1)
                sync_header += current_byte
                current_unpacked_byte = struct.unpack("!B", current_byte)[0]
                if current_unpacked_byte != sync_header_bytes[i]:
                    i = 0
                    sync_header = ''
                else:
                    i += 1


            syncless_header = sock.recv(6)

            data = ''
            chksum, length, frame_id, ack, end = decode_header(syncless_header)

            if length:
                data = sock.recv(length)


            frame = sync_header + syncless_header + data

            if not checksum(frame):
                unpacked_data = bytearray(struct.unpack("!%dB" % length, data))
                return chksum, length, frame_id, unpacked_data, ack, end
            else:
                current_sync = 0
                current_sync_unpacked = 0

        except socket.timeout:
            if resend_frame:
                print('TIMEOUT: Resending frame')
                sock.send(resend_frame)
                start_time = time.time()
        except Exception as e:
            raise e



def main(input_file, output_file, sock):
    frame_id = 0
    last_frame_id = 1
    last_checksum = 0
    recv_active = True
    send_active = True

    with open(output_file, 'wb') as out_file:
        with open(input_file, 'rb') as in_file:
            byte = in_file.read(PACKET_SIZE)
            if(byte == ''):
                send_active = False

            current_frame = build_frame(frame_id,bytearray(byte), end = (not send_active))
            sock.send(current_frame)
            # Get send time
            send_time = time.time()

            while current_frame or recv_active:
                print('Start of loop: ' + str(send_active) + ' ' + str(recv_active))

                try:
                    chksum, length, recv_frame_id, data, ack, end = recv_valid_synced_frame(sock, current_frame, send_time)
                except Exception as e:
                    print(str(e))
                    break

                if not ack:  # Data
                    print('Received Data - State: ' + str(send_active) + ' ' + str(recv_active))
                    if recv_frame_id != last_frame_id or chksum == last_checksum:

                        # if recv_active or (recv_frame_id == last_frame_id):
                        # New data
                        if recv_frame_id != last_frame_id and recv_active:
                            print('New data')
                            last_frame_id = recv_frame_id
                            last_checksum = chksum

                            # write data
                            out_file.write(data)

                            # Build new ACK frame
                            ack_frame = build_frame(recv_frame_id, ack = True)

                        print('Sending ACK - ' + str(recv_frame_id))
                        try:
                            # Send ack frame
                            sock.send(ack_frame)
                        except socket.error as e:
                            print("Socket error occured: " + str(e))
                        except Exception as e:
                            print(str(e))

                        if end:
                            print('Finishing receive')
                            recv_active = False

                elif ack and (not length) and current_frame:  # ACK
                    print('Received ACK: ' + str(send_active) + ' ' + str(recv_active))
                    # Check ACK
                    if recv_frame_id == frame_id:
                        print('ACK OK - ' + str(frame_id))
                        
                        if send_active:
                            byte = in_file.read(PACKET_SIZE)

                            # update frame_id
                            frame_id = int(not frame_id)

                            # No more data on file
                            if byte == '':
                                send_active = False

                            # build frame
                            current_frame = build_frame(frame_id,bytearray(byte),
                                            end = (not send_active))

                            try:
                                # Send current frame
                                sock.send(current_frame)
                                # get send time
                                send_time = time.time()
                            except socket.error as e:
                                print("Socket error occured: " + str(e))
                            except Exception as e:
                                print(str(e))
                        else:
                            current_frame = ''
                            print('Finishing Sending')

                    else:
                        print('ACK NOT OK: Expected ' + str(frame_id) + ' Received: ' + str(recv_frame_id))
    print('Finishing')



if __name__ == '__main__':

    if len(sys.argv) < 5:
        print('Insufficient number of arguments')

    if sys.argv[1] == '-c':
        conn_type = ACTIVE
        ip, port = sys.argv[2].split(':')
    elif sys.argv[1] == '-s':
        conn_type = PASSIVE
        ip = ''
        port = sys.argv[2]

    input_file = sys.argv[3]
    output_file = sys.argv[4]

    s = Emulator(conn_type, ip, int(port), input_file, output_file)
    s.start()
