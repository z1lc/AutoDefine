# AutoDefine Anki Add-on v.20180918
# Auto-defines words, optionally adding pronunciation and images.
#
# Copyright (c) 2014 - 2018 Robert Sanek    robertsanek.com    rsanek@gmail.com
# https://github.com/z1lc/AutoDefine                      Licensed under GPL v2

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

def get_definition(editor):
    # ideally, users wouldn't have to do this, but the API limit is just 1000 calls/day.
    # That could easily happen with just a few users.
    if MERRIAM_WEBSTER_API_KEY == "YOUR_KEY_HERE":
        message = "AutoDefine requires use of Merriam-Webster's Collegiate Dictionary with Audio API. " \
                  "To get functionality working:\n" \
                  "1. Go to www.dictionaryapi.com and sign up for an account, " \
                  "requesting access to the Collegiate Dictionary.\n" \
                  "2. In Anki, go to Tools > Add-Ons. Select AutoDefine, click \"Config\" on the right-hand side " \
                  "and replace YOUR_KEY_HERE with your unique API key.\n"
        showInfo(message)
        webbrowser.open("https://www.dictionaryapi.com/", 0, False)
        return

    editor.loadNote()
    word = clean_html(editor.note.fields[0]).strip()
    save_changes(editor, word, 0, True)

    url = "http://www.dictionaryapi.com/api/v1/references/collegiate/xml/" + word + "?key=" + MERRIAM_WEBSTER_API_KEY
    all_entries = []
    try:
        etree = ET.fromstring(urllib.request.urlopen(url).read())
        all_entries = etree.findall("entry")
    except URLError:
        showInfo("Didn't find definition for word '%s'\nUsing URL '%s'" % (word, url))

    definition_array = []

    if PRONUNCIATION_FIELD > -1:
        # Parse all unique pronunciations, and convert them to URLs as per http://goo.gl/nL0vte
        all_sounds = []
        for entry in all_entries:
            if entry.attrib["id"][:len(word) + 1] == word + "[" or entry.attrib["id"] == word:
                for wav in entry.findall("sound/wav"):
                    raw_wav = wav.text
                    # API-specific URL conversions
                    if raw_wav[:3] == "bix":
                        mid_url = "bix"
                    elif raw_wav[:2] == "gg":
                        mid_url = "gg"
                    elif raw_wav[:1].isdigit():
                        mid_url = "number"
                    else:
                        mid_url = raw_wav[:1]
                    wav_url = "http://media.merriam-webster.com/soundc11/" + mid_url + "/" + raw_wav
                    all_sounds.append(editor.urlToFile(wav_url).strip())

        # we want to make this a non-duplicate set, so that we only get unique sound files.
        all_sounds = OrderedSet(all_sounds)
        for soundLocalFilename in reversed(all_sounds):
            save_changes(editor, '[sound:' + soundLocalFilename + ']', PRONUNCIATION_FIELD)

    if DEFINITION_FIELD > -1:
        # Extract the type of word this is
        for entry in all_entries:
            if entry.attrib["id"][:len(word) + 1] == word + "[" or entry.attrib["id"] == word:
                this_def = entry.find("def")
                if entry.find("fl") is None:
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

                this_def.tail = "<b>" + fl + "</b>"  # save the functional label (noun/verb/etc) in the tail

                # the <ssl> tag will contain the word 'obsolete' if the term is not in use anymore. However, for some
                # reason, the tag precedes the <dt> that it is associated with instead of being a child. We need to
                # associate it here so that later we can either remove or keep it regardless.
                previous_was_ssl = False
                for child in this_def:
                    # this is a kind of poor way of going about things, but the ElementTree API
                    # doesn't seem to offer an alternative.
                    if child.text == "obsolete" and child.tag == "ssl":
                        previous_was_ssl = True
                    if previous_was_ssl and child.tag == "dt":
                        child.tail = "obsolete"
                        previous_was_ssl = False

                definition_array.append(this_def)

        to_return = ""
        for definition in definition_array:
            last_functional_label = ""
            for dtTag in definition.findall("dt"):

                if dtTag.tail == "obsolete":
                    dtTag.tail = ""  # take away the tail word so that when printing it does not show up.
                    if IGNORE_ARCHAIC:
                        continue

                # We don't really care for 'verbal illustrations' or 'usage notes',
                # even though they are occasionally useful.
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
                to_print = ET.tostring(dtTag, "", "xml").strip().decode("utf-8")
                # attempt to remove 'synonymous cross reference tag' and replace with semicolon
                to_print = to_print.replace("<sx>", "; ")
                # attempt to remove 'Directional cross reference tag' and replace with semicolon
                to_print = to_print.replace("<dx>", "; ")
                # remove all other XML tags
                to_print = re.sub('<[^>]*>', '', to_print)
                # remove all colons, since they are usually useless and have been replaced with semicolons above
                to_print = re.sub(':', '', to_print)
                # erase space between semicolon and previous word, if exists, and strip any extraneous whitespace
                to_print = to_print.replace(" ; ", "; ").strip()
                to_print += "<br>\n"

                # add verb/noun/adjective
                if last_functional_label != definition.tail:
                    to_print = definition.tail + " " + to_print
                last_functional_label = definition.tail
                to_return += to_print

        # final cleanup of <sx> tag bs
        to_return = to_return.replace(".</b> ; ", ".</b> ")  # <sx> as first definition after "n. " or "v. "
        to_return = to_return.replace("\n; ", "\n")  # <sx> as first definition after newline
        save_changes(editor, to_return, DEFINITION_FIELD)

    if OPEN_IMAGES_IN_BROWSER:
        webbrowser.open("https://www.google.com/search?q= " + word + "&safe=off&tbm=isch&tbs=isz:lt,islt:xga", 0, False)

    editor.web.eval("focusField(%d);" % 0)


# via https://github.com/sarajaksa/anki-addons/blob/master/edit-buttons.py#L79
def save_changes(editor, text, field_id, overwrite=False):
    if overwrite:
        editor.note.fields[field_id] = text
    else:
        editor.note.fields[field_id] += text
    editor.loadNote()
    editor.web.setFocus()
    editor.saveNow(lambda: None)
    editor.web.setFocus()
    editor.web.eval("focusField(%d);" % field_id)


# via https://stackoverflow.com/a/12982689
def clean_html(raw_html):
    return re.sub(re.compile('<.*?>'), '', raw_html)


def setup_buttons(buttons, editor):
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


addHook("setupEditorButtons", setup_buttons)

if getattr(mw.addonManager, "getConfig", None):
    config = mw.addonManager.getConfig(__name__)
    MERRIAM_WEBSTER_API_KEY = config['1 required']['MERRIAM_WEBSTER_API_KEY']
    PRONUNCIATION_FIELD = config['2 extra']['PRONUNCIATION_FIELD']
    DEFINITION_FIELD = config['2 extra']['DEFINITION_FIELD']
    IGNORE_ARCHAIC = config['2 extra']['IGNORE_ARCHAIC']
    OPEN_IMAGES_IN_BROWSER = config['2 extra']['OPEN_IMAGES_IN_BROWSER']
