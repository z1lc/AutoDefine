# AutoDefine Anki Add-on v.20141017
# Auto-defines words, optionally adding pronunciation and images.
# 
# Copyright (c) 2014 Robert Sanek        robertsanek.com       rsanek@gmail.com
# https://github.com/z1lc/AutoDefine                      Licensed under GPL v2

import AutoDefineAddon.core as core

# --------------------------------- SETTINGS ---------------------------------

# Get your unique API key by signing up at http://www.dictionaryapi.com/
core.MERRIAM_WEBSTER_API_KEY = "YOUR_KEY_HERE"

# Insert spoken pronunciations into the first field?
core.INSERT_PRONUNCIATIONS = True

# Ignore archaic/obsolete definitions?
core.IGNORE_ARCHAIC = True

# Open a browser tab with an image search for the same word?
core.OPEN_IMAGES_IN_BROWSER = False