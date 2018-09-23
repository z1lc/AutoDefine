# AutoDefine Anki Add-on v.20180921
# Auto-defines words, optionally adding pronunciation and images.
#
# Copyright (c) 2014 - 2018 Robert Sanek    robertsanek.com    rsanek@gmail.com
# https://github.com/z1lc/AutoDefine                      Licensed under GPL v2

import os
import platform
import re
import traceback
import urllib.error
import urllib.parse
import urllib.parse
import urllib.request
from urllib.error import URLError
from xml.etree import ElementTree as ET

from anki import version
from anki.hooks import addHook
from aqt import mw
from aqt.utils import showInfo, tooltip

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

# Index of field to insert pronunciations into (use -1 to turn off)
DEDICATED_INDIVIDUAL_BUTTONS = False


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

def get_definition(editor,
                   force_pronounce=False,
                   force_definition=False):
    editor.saveNow(lambda: _get_definition(editor, force_pronounce, force_definition))


def _get_definition(editor,
                    force_pronounce=False,
                    force_definition=False):
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

    word = clean_html(editor.note.fields[0]).strip()

    url = "http://www.dictionaryapi.com/api/v1/references/collegiate/xml/" + urllib.parse.quote_plus(word) + \
          "?key=" + MERRIAM_WEBSTER_API_KEY
    all_entries = []
    try:
        etree = ET.fromstring(urllib.request.urlopen(url).read())
        all_entries = etree.findall("entry")
    except URLError:
        showInfo("Didn't find definition for word '%s'\nUsing URL '%s'" % (word, url))
    except ET.ParseError:
        showInfo("Couldn't parse API response for word '%s'. "
                 "Please submit an issue to the AutoDefine GitHub (a web browser window will open)." % word)
        webbrowser.open("https://github.com/z1lc/AutoDefine/issues/new?title=Parse error for word '%s'"
                        "&body=Anki Version: %s%%0APlatform: %s %s%%0AURL: %s%%0AStack Trace: %s"
                        % (word, version, platform.system(), platform.release(), url, traceback.format_exc()), 0, False)

    if not all_entries:
        tooltip("No entry found in Merriam-Webster dictionary for word '%s'." % word)
        editor.web.eval("focusField(%d);" % 0)
        return
    definition_array = []

    if (not force_definition and PRONUNCIATION_FIELD > -1) or force_pronounce:
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
        for sound_local_filename in reversed(all_sounds):
            insert_into_field(editor, '[sound:' + sound_local_filename + ']', PRONUNCIATION_FIELD)

    if (not force_pronounce and DEFINITION_FIELD > -1) or force_definition:
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
        insert_into_field(editor, to_return, DEFINITION_FIELD)

    if OPEN_IMAGES_IN_BROWSER:
        webbrowser.open("https://www.google.com/search?q= " + word + "&safe=off&tbm=isch&tbs=isz:lt,islt:xga", 0, False)

    editor.web.eval("focusField(%d);" % 0)


def insert_into_field(editor, text, field_id, overwrite=False):
    if len(editor.note.fields) < field_id:
        tooltip("AutoDefine: Tried to insert '%s' into user-configured field number %d (0-indexed), but note type only "
                "has %d fields. Use a different note type with %d or more fields, or change the index in the "
                "Add-on configuration." % (text, field_id, len(editor.note.fields), field_id + 1), period=10000)
        return
    if overwrite:
        editor.note.fields[field_id] = text
    else:
        editor.note.fields[field_id] += text
    editor.loadNote()


# via https://stackoverflow.com/a/12982689
def clean_html(raw_html):
    return re.sub(re.compile('<.*?>'), '', raw_html)


def setup_buttons(buttons, editor):
    both_button = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "icon16.png"),
                                   cmd="AD",
                                   func=lambda s=editor: get_definition(editor),
                                   tip="AutoDefine Word (%s)" %
                                       ("no shortcut" if PRIMARY_SHORTCUT == "" else PRIMARY_SHORTCUT),
                                   toggleable=False,
                                   label="",
                                   keys=PRIMARY_SHORTCUT,
                                   disables=False)
    define_button = editor.addButton(icon="",
                                     cmd="D",
                                     func=lambda s=editor: get_definition(editor, force_definition=True),
                                     tip="AutoDefine: Definition only (%s)" %
                                         ("no shortcut" if DEFINE_ONLY_SHORTCUT == "" else DEFINE_ONLY_SHORTCUT),
                                     toggleable=False,
                                     label="",
                                     keys=DEFINE_ONLY_SHORTCUT,
                                     disables=False)
    pronounce_button = editor.addButton(icon="",
                                        cmd="P",
                                        func=lambda s=editor: get_definition(editor, force_pronounce=True),
                                        tip="AutoDefine: Pronunciation only (%s)" % ("no shortcut"
                                                                                     if PRONOUNCE_ONLY_SHORTCUT == ""
                                                                                     else PRONOUNCE_ONLY_SHORTCUT),
                                        toggleable=False,
                                        label="",
                                        keys=PRONOUNCE_ONLY_SHORTCUT,
                                        disables=False)
    buttons.append(both_button)
    if DEDICATED_INDIVIDUAL_BUTTONS:
        buttons.append(define_button)
        buttons.append(pronounce_button)
    return buttons


addHook("setupEditorButtons", setup_buttons)

if getattr(mw.addonManager, "getConfig", None):
    config = mw.addonManager.getConfig(__name__)
    MERRIAM_WEBSTER_API_KEY = config['1 required']['MERRIAM_WEBSTER_API_KEY']
    PRONUNCIATION_FIELD = config['2 extra']['PRONUNCIATION_FIELD']
    DEFINITION_FIELD = config['2 extra']['DEFINITION_FIELD']
    IGNORE_ARCHAIC = config['2 extra']['IGNORE_ARCHAIC']
    OPEN_IMAGES_IN_BROWSER = config['2 extra']['OPEN_IMAGES_IN_BROWSER']
    DEDICATED_INDIVIDUAL_BUTTONS = config['2 extra']['DEDICATED_INDIVIDUAL_BUTTONS']
    PRIMARY_SHORTCUT = config['3 shortcuts']['1 PRIMARY_SHORTCUT']
    DEFINE_ONLY_SHORTCUT = config['3 shortcuts']['2 DEFINE_ONLY_SHORTCUT']
    PRONOUNCE_ONLY_SHORTCUT = config['3 shortcuts']['3 PRONOUNCE_ONLY_SHORTCUT']
