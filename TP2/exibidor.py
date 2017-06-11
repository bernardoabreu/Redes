#!/usr/bin/env python

import sys
import socket
import struct

from message import Message
from message import MessageType


class Client():

    def __init__(self, host, port):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.id = 0
        self.server_id = 65535
        self.sequence_number = 0
        self.finish = False


    def open_connection(self):
        self.sock.connect((self.addr))
        msg = Message(self.id, self.server_id, self.sequence_number)
        msg.set_type(MessageType.OI)
        self.sock.send(str(msg))

        header = self.sock.recv(Message.HEADER_SIZE)

        if not header:
            self.finish = True
            return

        msg_type, source_id, dest_id, sequence_number = Message.decode_header(header)

        if(msg_type == MessageType.OK):
            self.id = dest_id


    def _handle_FLW(self):
        self.finish = True
        msg = Message(self.id, self.server_id, self.sequence_number)
        msg.set_type(MessageType.OK)
        self.sock.send(str(msg))
        self.sock.close()


    def _recv_header():
        header = self.sock.recv(Message.HEADER_SIZE)

        if not header:
            self.finish = True
            return -1
        else:
            return header

    def _handle_recv(self):
        try:
            header = self.sock.recv(Message.HEADER_SIZE)

            if not header:
                self.finish = True
                return

            msg_type, source_id, dest_id, sequence_number = Message.decode_header(header)

            if msg_type == MessageType.FLW:
                self._handle_FLW()
        except struct.error as e:

            sys.stderr.write('Error unpacking message: '+ str(e)+ '\n')


    def _finish(self):
        msg = Message(self.id, self.server_id, self.sequence_number)
        msg.set_type(MessageType.FLW)
        self.sock.send(str(msg))

        header = self.sock.recv(Message.HEADER_SIZE)

        if not header:
            self.finish = True
            return

        msg_type, source_id, dest_id, sequence_number = Message.decode_header(header)

        if msg_type == MessageType.OK:
            print 'ok'
        elif msg_type == MessageType.ERROR:
            print 'error'


    def run(self):
        try:
            self.open_connection()
            print('Seu identificador: ' + str(self.id))
            while not self.finish:

                self._handle_recv()
           
        except KeyboardInterrupt:
            self._finish()
        except socket.error, e:
            sys.stderr.write('SOCKET ERROR: '+ str(e)+ '\n')

        except Exception as e:
            sys.stderr.write('ERROR: '+ str(e)+ '\n')
        finally:
            self.sock.close()


if __name__ == '__main__':
    c = Client('127.0.0.1', 51515)
    c.run()