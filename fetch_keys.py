# Built-in modules
import threading, time

# Third-party modules
from playwright.sync_api import sync_playwright

def baidu_key ():
    with sync_playwright () as p:
        browser = p.chromium.launch ()
        page = browser.new_page ()
        page.goto ("https://maps.baidu.com", wait_until = "domcontentloaded")
        while True:
            if page.evaluate ("typeof SECKEY") != "undefined":
                key = page.evaluate ("SECKEY")
                if len (key) > 50: # Key is longer than 50 characters
                    print ("Baidu: " + key)
                    return
            time.sleep (0.1)

def tdt_key ():
    with sync_playwright () as p:
        browser = p.chromium.launch ()
        page = browser.new_page ()
        page.goto ("https://www.tianditu.gov.cn", wait_until = "domcontentloaded")
        while True:
            if page.evaluate ('typeof document.getElementsByClassName("leaflet-tile-loaded")[0]') != "undefined":
                key = page.evaluate ('new URLSearchParams(document.getElementsByClassName("leaflet-tile-loaded")[0].src).get("tk")')
                if len (key) == 32: # Key is 32 characters
                    print ("Tianditu: " + key)
                    return
            time.sleep (0.1)

with sync_playwright () as p:
    print ("Starting Baidu thread...")
    baidu = threading.Thread (target = baidu_key)
    baidu.start ()
    print ("Starting Tianditu thread...")
    tdt = threading.Thread (target = tdt_key)
    tdt.start ()