# Copyright (c) 2014 Robert Sanek / robertsanek.com / rsanek@gmail.com
# Licensed under GPLv2
# AutoDefine -- An add-on to Anki that auto-defines words, optionally adding pronunciation and images.

import urllib
import re
import credentials
from xml.etree import ElementTree as ET  # https://docs.python.org/2/library/xml.etree.elementtree.html

def get_definition(word):
    url = "http://www.dictionaryapi.com/api/v1/references/collegiate/xml/" + word + "?key=" + credentials.MERRIAM_WEBSTER_API_KEY
    etree = ET.parse(urllib.urlopen(url))
    allEntries = etree.findall("entry")
    definitionArray = []

    # Parse all unique pronunciations, and convert them to URLs as per http://goo.gl/nL0vte
    allSounds = []
    allSounds = set(allSounds)   # we want to make this a non-duplicate set, so that we only get unique sound files.
    for wav in etree.findall(".entry/sound/wav"):
        rawWav = wav.text
        if rawWav[:3] == "bix":
            midURL = "bix"
        elif rawWav[:2] == "gg":
            midURL = "gg"
        elif rawWav[:1].isdigit():
            midURL = "number"
        else:
            midURL = rawWav[:1]
        wavURL = "http://media.merriam-webster.com/soundc11/" + midURL + "/" + rawWav
        allSounds.add(wavURL)

    soundFiles = []
    #now, we can go out and fetch the sounds.
    for element in allSounds:
        response = urllib.urlopen(element)
        soundFiles.append(response.read())

    # Extract the type of word this is
    for entry in allEntries:
        if entry.attrib["id"][:len(word)+1] == word + "[" or entry.attrib["id"] == word:
            thisDef = entry.find("def")
            fl = entry.find("fl").text
            if fl == "verb":
                fl = "v."
            elif fl == "noun":
                fl = "n."
            elif fl == "adverb":
                fl = "adv."
            elif fl == "adjective":
                fl = "adj."

            thisDef.tail = fl  # save the functional label (noun/verb/etc) in the tail
            definitionArray.append(thisDef)

    toReturn = ""
    for definition in definitionArray:
        lastFunctionalLabel = ""
        toPrint = ""
        for dtTag in definition.findall("dt"):
            # we don't really care for 'verbal illustrations', even though they are occasionally useful.
            for verbalIllustration in dtTag.findall("vi"):
                dtTag.remove(verbalIllustration)

            toPrint = ET.tostring(dtTag, "", "xml").strip()
            toPrint = re.sub('<[^>]*>', '', toPrint)
            toPrint = re.sub(':', '', toPrint)
            toPrint += "\n"

            # add verb/noun/adjective
            if (lastFunctionalLabel != definition.tail):
                toPrint = definition.tail + " " + toPrint
                # but don't add an extra carriage return for the first definition
                if (definition != definitionArray[0]):
                    toPrint = "\n" + toPrint
            lastFunctionalLabel = definition.tail
            toReturn += toPrint

    return toReturn

print get_definition("ferment")