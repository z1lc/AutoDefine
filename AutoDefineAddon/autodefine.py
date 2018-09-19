# AutoDefine Anki Add-on v.20180918
# Auto-defines words, optionally adding pronunciation and images.
#
# Copyright (c) 2014 - 2018 Robert Sanek    robertsanek.com    rsanek@gmail.com
# https://github.com/z1lc/AutoDefine                      Licensed under GPL v2

# --------------------------------- SETTINGS ---------------------------------

# Get your unique API key by signing up at http://www.dictionaryapi.com/
MERRIAM_WEBSTER_API_KEY = "YOUR_KEY_HERE"

# Index of field to insert definitions into (use -1 to turn off)
DEFINITION_FIELD = 1

# Ignore archaic/obsolete definitions?
IGNORE_ARCHAIC = True

# Open a browser tab with an image search for the same word?
OPEN_IMAGES_IN_BROWSER = False

# Index of field to insert pronunciations into (use -1 to turn off)
PRONUNCIATION_FIELD = 0

# Dictionary API XML documentation: http://goo.gl/LuD83A
#
# http://www.dictionaryapi.com/api/v1/references/collegiate/xml/WORD?key=KEY
# Rough XML Structure:
# <entry_list>
#   <entry id="word[1]">
#     <sound>
#       <wav>soundfile.wav</wav>
#     </sound>
#     <fl>verb</fl>
#     <def>
#       <dt>:actual definition</dt>
#       <ssl>obsolete</ssl> (refers to next <dt>)
#       <dt>:another definition</dt>
#     </def>
#   </entry>
#   <entry id="word[2]">
#     ... (same structure as above)
#   </entry>
# </entry_list>
#
# ElementTree documentation: http://goo.gl/EcKhQv

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from urllib.error import URLError
from xml.etree import ElementTree as ET

from anki.hooks import addHook
from aqt import mw
from aqt.utils import showInfo

from .libs import webbrowser
from .libs.orderedset import OrderedSet


def get_definition(editor):
    # ideally, users wouldn't have to do this, but the API limit is just 1000 calls/day. That could easily happen with just a few users.
    if (MERRIAM_WEBSTER_API_KEY == "YOUR_KEY_HERE"):
        message = "AutoDefine requires use of Merriam-Webster's Collegiate Dictionary with Audio API. To get functionality working:\n"
        message += "1. Go to www.dictionaryapi.com and sign up for an account, requesting access to the Collegiate Dictionary.\n"
        message += "2. In Anki, go to Tools > Add-Ons. Select AutoDefine, click \"Config\" on the right-hand side and replace YOUR_KEY_HERE with your unique API key.\n"
        showInfo(message)
        webbrowser.open("https://www.dictionaryapi.com/", 0, False)
        return

    editor.loadNote()
    word = cleanhtml(editor.note.fields[0]).strip()
    saveChanges(editor, word, 0, True)

    url = "http://www.dictionaryapi.com/api/v1/references/collegiate/xml/" + word + "?key=" + MERRIAM_WEBSTER_API_KEY
    allEntries = []
    try:
        etree = ET.fromstring(urllib.request.urlopen(url).read())
        allEntries = etree.findall("entry")
    except URLError as e:
        showInfo("Didn't find definition for word '%s'\nUsing URL '%s'" % (word, url))

    definitionArray = []

    if (PRONUNCIATION_FIELD > -1):
        # Parse all unique pronunciations, and convert them to URLs as per http://goo.gl/nL0vte
        allSounds = []
        for entry in allEntries:
            if entry.attrib["id"][:len(word) + 1] == word + "[" or entry.attrib["id"] == word:
                for wav in entry.findall("sound/wav"):
                    rawWav = wav.text
                    # API-specific URL conversions
                    if rawWav[:3] == "bix":
                        midURL = "bix"
                    elif rawWav[:2] == "gg":
                        midURL = "gg"
                    elif rawWav[:1].isdigit():
                        midURL = "number"
                    else:
                        midURL = rawWav[:1]
                    wavURL = "http://media.merriam-webster.com/soundc11/" + midURL + "/" + rawWav
                    allSounds.append(editor.urlToFile(wavURL).strip())

        # we want to make this a non-duplicate set, so that we only get unique sound files.
        allSounds = OrderedSet(allSounds)
        for soundLocalFilename in reversed(allSounds):
            saveChanges(editor, '[sound:' + soundLocalFilename + ']', PRONUNCIATION_FIELD)

    if (DEFINITION_FIELD > -1):
        # Extract the type of word this is
        for entry in allEntries:
            if entry.attrib["id"][:len(word) + 1] == word + "[" or entry.attrib["id"] == word:
                thisDef = entry.find("def")
                if entry.find("fl") == None:
                    continue
                fl = entry.find("fl").text
                if fl == "verb":
                    fl = "v."
                elif fl == "noun":
                    fl = "n."
                elif fl == "adverb":
                    fl = "adv."
                elif fl == "adjective":
                    fl = "adj."

                thisDef.tail = "<b>" + fl + "</b>"  # save the functional label (noun/verb/etc) in the tail

                # the <ssl> tag will contain the word 'obsolete' if the term is not in use anymore. However, for some reason, the tag
                # precedes the <dt> that it is associated with instead of being a child. We need to associate it here so that later
                # we can either remove or keep it regardless.
                previousWasSSL = False
                for child in thisDef:
                    # this is a kind of poor way of going about things, but the ElementTree API doesn't seem to offer an alternative.
                    if child.text == "obsolete" and child.tag == "ssl":
                        previousWasSSL = True
                    if previousWasSSL and child.tag == "dt":
                        child.tail = "obsolete"
                        previousWasSSL = False

                definitionArray.append(thisDef)

        toReturn = ""
        for definition in definitionArray:
            lastFunctionalLabel = ""
            toPrint = ""
            for dtTag in definition.findall("dt"):

                if dtTag.tail == "obsolete":
                    dtTag.tail = ""  # take away the tail word so that when printing it does not show up.
                    if IGNORE_ARCHAIC:
                        continue

                # We don't really care for 'verbal illustrations' or 'usage notes', even though they are occasionally useful.
                for usageNote in dtTag.findall("un"):
                    dtTag.remove(usageNote)
                for verbalIllustration in dtTag.findall("vi"):
                    dtTag.remove(verbalIllustration)

                # Directional cross reference doesn't make sense for us
                for dxTag in dtTag.findall("dx"):
                    for dxtTag in dxTag.findall("dxt"):
                        for dxnTag in dxtTag.findall("dxn"):
                            dxtTag.remove(dxnTag)

                # extract raw XML from <dt>...</dt>
                toPrint = ET.tostring(dtTag, "", "xml").strip().decode("utf-8")
                # attempt to remove 'synonymous cross reference tag' and replace with semicolon
                toPrint = toPrint.replace("<sx>", "; ")
                # attempt to remove 'Directional cross reference tag' and replace with semicolon
                toPrint = toPrint.replace("<dx>", "; ")
                # remove all other XML tags
                toPrint = re.sub('<[^>]*>', '', toPrint)
                # remove all colons, since they are usually useless and have been replaced with semicolons above
                toPrint = re.sub(':', '', toPrint)
                # erase space between semicolon and previous word, if exists, and strip any extraneous whitespace
                toPrint = toPrint.replace(" ; ", "; ").strip()
                toPrint += "<br>\n"

                # add verb/noun/adjective
                if (lastFunctionalLabel != definition.tail):
                    toPrint = definition.tail + " " + toPrint
                    # but don't add an extra carriage return for the first definition
                    # if (definition != definitionArray[0]):
                    #    toPrint = "<br>\n" + toPrint
                lastFunctionalLabel = definition.tail
                toReturn += toPrint

        # final cleanup of <sx> tag bs
        toReturn = toReturn.replace(".</b> ; ", ".</b> ")  # <sx> as first definition after "n. " or "v. "
        toReturn = toReturn.replace("\n; ", "\n")  # <sx> as first definition after newline
        saveChanges(editor, toReturn, DEFINITION_FIELD)

    if (OPEN_IMAGES_IN_BROWSER):
        webbrowser.open("https://www.google.com/search?q= " + word + "&safe=off&tbm=isch&tbs=isz:lt,islt:xga", 0, False)

    editor.web.eval("focusField(%d);" % 0)

# via https://github.com/sarajaksa/anki-addons/blob/master/edit-buttons.py#L79
def saveChanges(editor, text, id, overwrite=False):
    if (overwrite):
        editor.note.fields[id] = text
    else:
        editor.note.fields[id] += text
    editor.loadNote()
    editor.web.setFocus()
    editor.saveNow(lambda: None)
    editor.web.setFocus()
    editor.web.eval("focusField(%d);" % id)

# via https://stackoverflow.com/a/12982689
def cleanhtml(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

def mySetupButtons(buttons, editor):
    b = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "icon16.png"),
                         cmd="AD",
                         func=lambda s=editor: get_definition(editor),
                         tip="AutoDefine Word (Ctrl+E)",
                         toggleable=False,
                         label="",
                         keys="ctrl+e",
                         disables=False)
    buttons.append(b)
    return buttons

addHook("setupEditorButtons", mySetupButtons)

if getattr(mw.addonManager, "getConfig", None):
    config = mw.addonManager.getConfig(__name__)
    MERRIAM_WEBSTER_API_KEY = config['1 required']['MERRIAM_WEBSTER_API_KEY']
    PRONUNCIATION_FIELD = config['2 extra']['PRONUNCIATION_FIELD']
    DEFINITION_FIELD = config['2 extra']['DEFINITION_FIELD']
    IGNORE_ARCHAIC = config['2 extra']['IGNORE_ARCHAIC']
    OPEN_IMAGES_IN_BROWSER = config['2 extra']['OPEN_IMAGES_IN_BROWSER']
