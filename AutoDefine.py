import urllib
import re
import credentials
from xml.dom import minidom


def get_definition(word):
    url = "http://www.dictionaryapi.com/api/v1/references/collegiate/xml/" + word + "?key=" + credentials.MERRIAM_WEBSTER_API_KEY
    dom = minidom.parse(urllib.urlopen(url))
    for node in dom.getElementsByTagName("dt"):
        indivDef = re.sub('<[^>]*>', '', node.toxml())
        print indivDef
    #return data[0].toxml()
    #return dom.toxml()

get_definition("heart")