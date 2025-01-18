# Built-in modules
import re, threading, time

# Third-party modules
from playwright.sync_api import sync_playwright
import requests as r

keys = {}

def baidu_key ():
    global keys
    with sync_playwright () as p:
        browser = p.chromium.launch ()
        page = browser.new_page ()
        page.goto ("https://maps.baidu.com", wait_until = "domcontentloaded")
        while True:
            if page.evaluate ("typeof SECKEY") != "undefined":
                keys ["baidu"] = page.evaluate ("SECKEY")
                if len (keys ["baidu"]) > 50: # Key is longer than 50 characters
                    return
            time.sleep (0.1)

with sync_playwright () as p:
    print ("Starting Baidu thread...")
    baidu = threading.Thread (target = baidu_key)
    baidu.start ()
    print ("Starting Tianditu thread...")
    page = r.get ("https://www.tianditu.gov.cn/").text
    keys ["tdt"] = re.search (r'(maptoken.+?")([0-9a-f]+)', page).group (2)
    print ("Tianditu thread finished.")
    baidu.join ()
    print ("Baidu thread finished.")

print (f"Baidu: {keys ['baidu']}\nTianditu: {keys ['tdt']}")