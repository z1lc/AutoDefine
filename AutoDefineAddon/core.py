# Copyright (c) 2014 Robert Sanek        robertsanek.com       rsanek@gmail.com
# https://github.com/z1lc/AutoDefine                      Licensed under GPL v2
# 
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

import urllib
import re
from xml.etree import ElementTree as ET
import collections
import webbrowser as webbrowser

from anki.hooks import wrap, addHook
from aqt.editor import Editor
from aqt.utils import showInfo
from anki.utils import json

def get_definition(editor):
    # ideally, users wouldn't have to do this, but the API limit is just 1000 calls/day. That could easily happen with just a few users.
    if (MERRIAM_WEBSTER_API_KEY == "YOUR_KEY_HERE"):
        message = "AutoDefine requires use of Merriam-Webster's Collegiate Dictionary with Audio API. To get functionality working:\n"
        message += "1. Go to www.dictionaryapi.com and sign up for an account, requesting access to the Collegiate Dictionary.\n"
        message += "2. In Anki, go to Tools>Add-Ons>AutoDefine>Edit... and replace YOUR_KEY_HERE with your unique API key.\n"
        showInfo(message)
        return

    # Random Anki loading
    editor.loadNote()
    editor.web.setFocus()
    editor.web.eval("focusField(0);")
    editor.web.eval("caretToEnd();")
    allFields = editor.note.fields

    word = allFields[0]

    url = "http://www.dictionaryapi.com/api/v1/references/collegiate/xml/" + word + "?key=" + MERRIAM_WEBSTER_API_KEY
    etree = ET.parse(urllib.urlopen(url))
    allEntries = etree.findall("entry")

    definitionArray = []

    if (INSERT_PRONUNCIATIONS):
        # Parse all unique pronunciations, and convert them to URLs as per http://goo.gl/nL0vte
        allSounds = []
        for entry in allEntries:
            if entry.attrib["id"][:len(word)+1] == word + "[" or entry.attrib["id"] == word:
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
            allFields[0] += '[sound:' + soundLocalFilename + ']'

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

            thisDef.tail = "<b>" + fl + "</b>" # save the functional label (noun/verb/etc) in the tail

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
                dtTag.tail = "" #take away the tail word so that when printing it does not show up.
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

            toPrint = ET.tostring(dtTag, "", "xml").strip() # extract raw XML from <dt>...</dt>
            toPrint = toPrint.replace("<sx>", "; ") # attempt to remove 'synonymous cross reference tag' and replace with semicolon
            toPrint = toPrint.replace("<dx>", "; ") # attempt to remove 'Directional cross reference tag' and replace with semicolon
            toPrint = re.sub('<[^>]*>', '', toPrint) # remove all other XML tags
            toPrint = re.sub(':', '', toPrint) # remove all colons, since they are usually useless and have been replaced with semicolons above
            toPrint = toPrint.replace(" ; ", "; ").strip() # erase space between semicolon and previous word, if exists, and strip any extraneous whitespace
            toPrint += "<br>\n"

            # add verb/noun/adjective
            if (lastFunctionalLabel != definition.tail):
                toPrint = definition.tail + " " + toPrint
                # but don't add an extra carriage return for the first definition
                #if (definition != definitionArray[0]):
                #    toPrint = "<br>\n" + toPrint
            lastFunctionalLabel = definition.tail
            toReturn += toPrint

    # final cleanup of <sx> tag bs
    toReturn = toReturn.replace(".</b> ; ", ".</b> ") #<sx> as first definition after "n. " or "v. "
    toReturn = toReturn.replace("\n; ", "\n") #<sx> as first definition after newline

    allFields[1] = toReturn
    editor.web.eval("setFields(%s, %d);" % (allFields, 0))

    # not sure exactly how saving works, but focusing different fields seems to help.
    editor.loadNote()
    editor.web.eval("focusField(0);")
    editor.web.eval("focusField(1);")
    editor.web.eval("focusField(0);")
    if (OPEN_IMAGES_IN_BROWSER):
        webbrowser.open("https://www.google.com/search?q= "+ word + "&safe=off&tbm=isch&tbs=isz:lt,islt:xga", 0, False)


def mySetupButtons(editor):
    editor._addButton("AutoDefine", lambda ed=editor: get_definition(ed),
                    text="AD", tip="AutoDefine Word (Ctrl+E)", key="Ctrl+e")

Editor.get_definition = get_definition
addHook("setupEditorButtons", mySetupButtons)


# via http://code.activestate.com/recipes/576694/
class OrderedSet(collections.MutableSet):

    def __init__(self, iterable=None):
        self.end = end = [] 
        end += [None, end, end]         # sentinel node for doubly linked list
        self.map = {}                   # key --> [key, prev, next]
        if iterable is not None:
            self |= iterable

    def __len__(self):
        return len(self.map)

    def __contains__(self, key):
        return key in self.map

    def add(self, key):
        if key not in self.map:
            end = self.end
            curr = end[1]
            curr[2] = end[1] = self.map[key] = [key, curr, end]

    def discard(self, key):
        if key in self.map:        
            key, prev, next = self.map.pop(key)
            prev[2] = next
            next[1] = prev

    def __iter__(self):
        end = self.end
        curr = end[2]
        while curr is not end:
            yield curr[0]
            curr = curr[2]

    def __reversed__(self):
        end = self.end
        curr = end[1]
        while curr is not end:
            yield curr[0]
            curr = curr[1]

    def pop(self, last=True):
        if not self:
            raise KeyError('set is empty')
        key = self.end[1][0] if last else self.end[2][0]
        self.discard(key)
        return key

    def __repr__(self):
        if not self:
            return '%s()' % (self.__class__.__name__,)
        return '%s(%r)' % (self.__class__.__name__, list(self))

    def __eq__(self, other):
        if isinstance(other, OrderedSet):
            return len(self) == len(other) and list(self) == list(other)
        return set(self) == set(other)