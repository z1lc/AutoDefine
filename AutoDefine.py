import urllib
import re
import credentials
from xml.etree import ElementTree as ET

def get_definition(word):
    url = "http://www.dictionaryapi.com/api/v1/references/collegiate/xml/" + word + "?key=" + credentials.MERRIAM_WEBSTER_API_KEY
    etree = ET.parse(urllib.urlopen(url))
    allEntries = etree.findall("entry")
    definitionArray = []
    for entry in allEntries:
        if entry.attrib["id"][:len(word)+1] == word + "[" or entry.attrib["id"] == word:
            thisDef = entry.find("def")
            fl = entry.find("fl").text
            if (fl == "verb"):
                fl = "v."
            elif (fl == "noun"):
                fl = "n."
            elif (fl == "adverb"):
                fl = "adv."
            elif (fl == "adjective"):
                fl = "adj."

            thisDef.tail = fl  # save the functional label (noun/verb/etc) in the tail
            definitionArray.append(thisDef)
            
    for definition in definitionArray:
        lastFunctionalLabel = ""
        for dtTag in definition.findall("dt"):
            # we don't really care for 'verbal illustrations', even though they are occassionally useful.
            for verbalIllustration in dtTag.findall("vi"):
                dtTag.remove(verbalIllustration)

            toPrint = ET.tostring(dtTag, "", "xml").strip()
            toPrint = re.sub('<[^>]*>', '', toPrint)
            toPrint = re.sub(':', '', toPrint)
            if (lastFunctionalLabel != definition.tail):
                toPrint = definition.tail + " " + toPrint
            lastFunctionalLabel = definition.tail
            print toPrint
        #print ET.dump(etree.find("def"))
        #return data[0].toxml()
        #return dom.toxml()

get_definition("ferment")