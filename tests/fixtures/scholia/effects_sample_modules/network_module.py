"""Sample module exercising the network detector."""
import socket
import urllib.request

import requests


def fetch(url):
    return requests.get(url).text


def fetch_via_urllib(url):
    return urllib.request.urlopen(url).read()


def make_socket():
    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)
