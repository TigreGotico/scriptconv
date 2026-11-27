"""Text -> the words to say and the punctuation marks between them.

Everything that is not a plain word is turned into words here, by rule:
numbers, ordinals, money, dates, times, telephone numbers, units,
abbreviations, initialisms, symbols, chat spellings, version numbers, codes
and reference numbers, web addresses and file names.
Emoticons and emoji are dropped: they are neither read nor a pause.
A pronunciation can be given inline, ``{HH AH0 L OW1}`` or ``{h ə l ˈoʊ}``,
alone or right after the word it replaces. Braces that hold anything else are
read as text.

The result is a list of ``Word`` and ``Punct`` tokens. Hand-written tables in
``data/`` hold the abbreviations, units, chat spellings and file endings.
"""

import re
from typing import NamedTuple
import unicodedata

from .symbols import PUNCTUATION
from . import tables
from .convert import convert, from_text, is_arpabet


class Word(NamedTuple):
    text: str                 # letters and apostrophes, lower case
    attach: bool = False      # continues the previous word (hyphenated compound, parts of one token)
    raw: str = ""             # as written
    spell: bool = False       # read letter by letter
    phones: tuple = None      # pronunciation given inline by the user


class Punct(NamedTuple):
    mark: str


# Private-use characters that carry decisions through the rewriting of the text:
# letters to be named sit between _SPELL and _END, and an inline pronunciation
# is a single character (its number added to _INLINE_BASE) between two _INLINE.
_SPELL, _END, _INLINE, _INLINE_BASE = "", "", "", 0xE100
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_SCALES = ("thousand", "million", "billion", "trillion", "quadrillion", "quintillion")
_ORDINAL = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
            "twelve": "twelfth"}
_MONTHS = "January February March April May June July August September October November December".split()
_MONTH_NUMBER = {name.lower()[:3]: index + 1 for index, name in enumerate(_MONTHS)}
_MONTH_PATTERN = "|".join(_MONTHS) + "|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
_DAY_NAMES = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday",
              "sun": "Sunday"}
_DAY_PATTERN = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Thurs|Thur|Tues|Mon|Tue|Wed|Thu|Fri|Sat|Sun"
_CURRENCY = {"$": ("dollar", "dollars", "cent", "cents"), "£": ("pound", "pounds", "penny", "pence"),
             "€": ("euro", "euros", "cent", "cents"), "¥": ("yen", "yen", "", ""), "₹": ("rupee", "rupees", "paisa", "paise")}
_CURRENCY.update({"USD": _CURRENCY["$"], "EUR": _CURRENCY["€"], "GBP": _CURRENCY["£"], "JPY": _CURRENCY["¥"],
                  "INR": _CURRENCY["₹"], "CHF": ("Swiss franc", "Swiss francs", "centime", "centimes"),
                  "CAD": ("Canadian dollar", "Canadian dollars", "cent", "cents"),
                  "AUD": ("Australian dollar", "Australian dollars", "cent", "cents"), "CNY": ("yuan", "yuan", "", "")})
_CURRENCY_CODES = "USD|EUR|GBP|JPY|INR|CHF|CAD|AUD|CNY"
_SCALE_LETTER = {"k": "thousand", "m": "million", "b": "billion", "bn": "billion", "t": "trillion"}
_FRACTION = {2: ("half", "halves"), 4: ("quarter", "quarters")}
_SYMBOL_WORDS = {"&": "and", "@": "at", "+": "plus", "=": "equals", "%": "percent", "×": "times", "÷": "divided by",
                 "±": "plus or minus", "©": "copyright", "§": "section", "°": "degrees",
                 "≥": "greater than or equal to", "≤": "less than or equal to", "≠": "not equal to", "≈": "approximately",
                 "∞": "infinity", "√": "square root of", "π": "pi"}
_COMPARISONS = {">=": "greater than or equal to", "<=": "less than or equal to", "!=": "not equal to"}
# Capitals read letter by letter although they also spell a word.
_INITIALISMS = frozenset("US IT AI ID UN EU UK LA AD BC AM PM OS PE PA MA LED SAT RIP ER".split())
# Sounds written without a vowel. "Ss" among them, or alone, is a hiss ("Sh! Ss! Tsk!").
_SOUNDS = frozenset("sh shh ss zz hm hmm mm tsk psst pfft hmph psh pssh".split())
# A comparison between two values is said with "is": "67 > 66" is "sixty seven
# is greater than sixty six", "see if b>a" is "see if B is greater than A". A
# value is a figure, a single letter or a closing bracket, with the same space
# (or none) on both sides of the sign. "Is" is left out where the comparison
# only describes the value: "for n > 4", "any q > 0", "an integer k ≥ 2". The
# mark below is put after the first value and stays there while the figures
# around it are turned into words.
_IS = chr(0xE006)
_COMPARED = re.compile(r"(?P<gap>[ \t]?)(?P<sign>>=|<=|!=|[<>≥≤≠])(?P=gap)")
_VALUE_BEFORE = re.compile(r"(?:(?<![\w.,])\d[\d.,]*%?|(?<![\w'’.-])[A-Za-z]|[)\]])$")
_VALUE_AFTER = re.compile(r"(?:[-+]?[$£€¥₹]?\d[\d.,]*%?(?!\w)|\.\d|[A-Za-z](?![\w'’])|[(\[])")
_CLAUSE_OPENERS = frozenset("if elif while when whenever where whether that because since as and or but so then think thinks "
                            "thought know knows say says said suppose assume means implies hence thus therefore although though "
                            "unless until once else also clearly obviously indeed here now again first next finally similarly "
                            "otherwise however moreover".split())
# "A", "a" and the small letters chat writes for a word ("k", "u", "r") are read
# as words. Beside a sign or alone in brackets they stand for something and are
# named: "a=10", "b>a", "k = k + 1", "(a)". After "=" or a spaced sign the letter
# must not open a phrase ("mode = a set of notes").
_SIGN = r"[<>+*/^≤≥≠≈×÷±]"
_SPACED_SIGN = r" [<>+*≤≥≠≈×÷±] "
_NO_PHRASE = r"(?![\w'’-]|\s+(?!(?:and|or|then|if|when|where|while|for|is|are|was|but|so|in|to)\b)[A-Za-z])"
_LETTER_PLACES = tuple(re.compile(pattern) for pattern in (
    r"(?<![\w'’.-])(?P<letter>[Aakur])(?=" + _IS + r"?\s?[<>!=]?=)",                     # a=10, a = 10, a >= b
    r"[<>!=]?=\s?(?P<letter>[Aakur])" + _NO_PHRASE,                                      # x=a, c = a + b
    r"(?<![\w'’.-])(?P<letter>[Aakur])(?=" + _IS + r"?" + _SIGN + r"(?:[\w($]|\.\d))",   # a>b, a+b, a/b, a^2
    r"(?<=[\w)" + _IS + r"]" + _SIGN + r")(?<![Ww]/)(?P<letter>[Aakur])(?![\w'’-])",     # b>a, 1/a; not "w/a friend"
    r"(?<![\w'’.-])(?P<letter>[Aakur])(?=" + _IS + r"?" + _SPACED_SIGN + r"(?:[A-Za-z]|\d[\d.,]*)(?![\w'’]))",   # a > b
    r"(?<![\w'’.])(?:[A-Za-z]|\d[\d.,]*)" + _IS + r"?" + _SPACED_SIGN + r"(?P<letter>[Aakur])" + _NO_PHRASE,    # b > a
    r"(?<=\()(?P<letter>[Aakur])(?=\)|, )",                                              # (a), f(a, b)
    r"(?<=, )(?P<letter>[Aakur])(?=\))",                                                 # f(b, a)
    r"(?:(?<=\s)|^)(?P<letter>[akur])(?=\)\s)",                                          # a) the first point
))
# "<b>", "</p>", "<your name>", "Vec<u64>", "map<int, int>": angle brackets that
# enclose something. The "<" and ">" that are left may compare two things.
_ANGLES = re.compile(r"(?<![\w)" + _END + _IS + r"])<[A-Za-z0-9/!?][^<>(){}+*;|\n]*>"
                     r"|(?<=[\w" + _END + _IS + r"])<[^<>(){}+*;|\n]{1,80}>(?![\w$])"
                     r"|</?[A-Za-z][\w-]+/?>")
_ANGLE_MARK = chr(0xE005)


def _without_angles(text):
    """``text`` with the angle brackets that enclose something replaced by a
    mark, one for one, the inner ones first."""
    while "<" in text and ">" in text:
        marked = _ANGLES.sub(lambda match: _ANGLE_MARK + match.group(0)[1:-1] + _ANGLE_MARK, text)
        if marked == text:
            break
        text = marked
    return text


# "<" or ">" with no space on either side: "b>a", "x<5", "p<.05". It is read as a
# comparison when a figure stands on one side, or a single letter or a bracket on
# both. "File>Open" and "M>Train" are not comparisons.
_JOINED_COMPARISON = re.compile(r"(?<=[\w)" + _END + _IS + r"])[<>](?=[\w(" + _SPELL + r"]|\.\d| minus \d)")
_FIGURE_BEFORE = re.compile(r"(?<![\w.,])\d[\d.,]*%?$")
_FIGURE_AFTER = re.compile(r"(?:\d[\d.,]*%?(?!\w)|\.\d| minus \d)")
_LETTER_BEFORE = re.compile(r"(?:(?<![\w'’.])[A-Za-z]|[)" + _END + r"])$")
_LETTER_AFTER = re.compile(r"(?:[A-Za-z](?![\w'’])|[(" + _SPELL + r"])")
_SENTENCE_STARTERS = frozenset("the he she it i we they this that there but and in on at a an if when what why how who my our "
                               "you then so now after before however".split())
_YEAR_CONTEXT = frozenset("in since by from until till before after during around circa of year early late mid summer winter "
                          "spring fall autumn class".split())
_CARDINAL_AFTER = frozenset("war chapter part book volume act scene section phase type class level stage title article "
                            "appendix world".split())
_LABELLED = frozenset("plan vitamin grade type option class section part team group exhibit appendix point model series "
                      "hepatitis level".split())
_ROMAN = {"II": 2, "III": 3, "IV": 4, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "XI": 11, "XII": 12, "XIII": 13, "XIV": 14,
          "XV": 15, "XVI": 16, "XVIII": 18, "XX": 20}
_LEADING_APOSTROPHE = frozenset(("'em", "'tis", "'twas", "'til", "'cause", "'bout", "'round", "'n"))
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿\U0001F1E6-\U0001F1FF←-⇿⬀-⯿️‍⃣]+")
_EMOTICON = re.compile(
    r"(?<![A-Za-z0-9])(?:[:;=]['^-]?[DPpOo3|/\\*\]\[}{><]+|[)(\]\[][-^']?[:;=]|<3+|</3|\^_?\^|-_-|[oO]_[oO]|>_<|T_T|\\o/|:'[()])(?![A-Za-z0-9])"
    r"|[:;]['^-]?[)(]+"
    r"|(?<![A-Za-z0-9)])=['^-]?[)(]+|=['^-]?[)(]+(?![A-Za-z0-9(.$-])"            # "=(" is a face, but not in "y=(a+b)"
    r"|(?<=[A-Za-z]{2})<3+(?![.,]?\d)")                                          # a heart joined to a word: "you<3"

# Words that say what the number after them is. A telephone number, a PIN or a
# reference is read digit by digit; an amount is not.
_PHONE_WORDS = frozenset("call dial ring phone telephone tel mobile cell fax hotline text sms whatsapp".split())
_PHONE_LINKS = frozenset("to on at or us me him her them back".split())
_PIN_WORDS = frozenset("code pin extension ext passcode password zip postcode cvv cvc otp".split())
_STRONG_WORDS = frozenset("number id reference ref serial account tracking booking confirmation".split())
_WEAK_WORDS = frozenset("order ticket invoice case claim policy receipt transaction parcel shipment container payment "
                        "reservation membership customer batch lot item job issue bug request".split())
_LINK_WORDS = frozenset("is was are were ends ending in with starts starting begins beginning".split())
_NOT_COUNTED = frozenset("is was has does goes ships arrives departs leaves shows needs blocks remains includes contains "
                         "says reads starts ends closes opens runs takes comes this his its us as yes plus minus less".split())
_NUMBERED = frozenset("ref reference serial account order invoice tracking part model phone tel fax id room flight case "
                      "ticket policy licence license booking customer vat tax reg registration".split())
_DATE_BEFORE = frozenset("on dated due until till by since from before after for shipped delivered arriving arrives arrive "
                         "arrived expires expired ends ending starts starting begins beginning monday tuesday wednesday "
                         "thursday friday saturday sunday mon tue tues wed thu thur thurs fri sat sun".split())
_CLASSIC_FRACTIONS = frozenset((2, 3, 4, 5, 6, 8, 10, 16, 32, 64, 100))
_RATIO_WORDS = frozenset("ratio ratios scale odds aspect mix split proportion".split())
_DURATION_WORDS = frozenset("lasted took duration runtime recording video clip track lap pace length long".split())
_CLOCK_WORDS = frozenset("window slot open opens opening hours shift session served service available booked appointment "
                         "delivery arrive arrives arriving".split())
_CAPITAL_WORDS = frozenset("IN ON AT TO OF BY OR IS AS IF NO SO WE HE MY ME DO GO UP AN AM PM BE IT US THE AND FOR BUT NOT "
                           "ALL".split())
_SHORT_WORDS = frozenset("my to in on of go up no do me we us it is at by be so or an as if he hi ok".split())
_ZONES = "ET|CT|MT|PT|EST|EDT|CST|CDT|MST|MDT|PST|PDT|GMT|UTC|BST|CET|CEST|IST|AEST|AEDT|JST"
_SIZES = "XXXL|XXL|XXS|XL|XS|S|M|L"
_LENGTHS = "mm|cm|km|m|ft|in|inch|inches|feet|foot|metres?|meters?|yards?|yd|px|pixels?"
# Before a number these mean a version: its parts are read as whole numbers ("three point twelve").
_VERSIONED = ("version|ver|release|firmware|patch|kernel|build|python|node|nodejs|ios|ipados|macos|watchos|tvos|android|"
              "chrome|firefox|safari|java|php|ruby|rust|swift|kotlin|golang|django|rails|react|angular|vue|docker|"
              "kubernetes|ubuntu|debian|fedora|windows|linux|postgres|postgresql|mysql|redis|numpy|pytorch|tensorflow|cuda|"
              "xcode|gcc|clang|unity|minecraft|typescript|bluetooth|usb|hdmi|opengl|vulkan|directx|"
              "upgrade[ds]?|update[ds]?|downgrade[ds]?")
_SEPARATORS = {".": "dot", "/": "slash", "@": "at", "-": "dash", "_": "underscore", ":": "colon", "=": "equals", "&": "and",
               "+": "plus"}
_HALF_DAY = r"(?:\s?([AaPp])\.[Mm]\.?|\s?([AaPp])[Mm]\b)"
_AMOUNT = r"(?P<whole>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<fraction>\d+))?"
_MONEY = re.compile(r"(?:(?<![\w.])(?P<minus>-)\s?)?(?P<symbol>[$£€¥₹]|(?<![A-Za-z])(?:" + _CURRENCY_CODES + r")(?![A-Za-z]))\s?"
                    r"(?P<inner>-)?" + _AMOUNT + r"(?:\s?(?P<scale>thousand|million|billion|trillion|bn|[kKmMbB])(?![A-Za-z]))?")
# A currency written after the amount: "20 €", "20€", "12.50 EUR". Those who write
# it there often part the thousands with spaces: "750 000 $".
_SIGN_AFTER = r"[$£€¥₹](?![\w$£€¥₹])|(?:" + _CURRENCY_CODES + r")(?![A-Za-z])"
_MONEY_AFTER = re.compile(r"(?:(?<![\w.])(?P<minus>-)\s?)?(?<![\w.,^])"
                          r"(?P<whole>\d{1,3}(?:,\d{3})+|[1-9]\d{0,2}(?: \d{3})+|\d+)(?:\.(?P<fraction>\d+))?"
                          r"\s?(?P<symbol>" + _SIGN_AFTER + r")")
_RANGE_BEFORE_SIGN = re.compile(r"(?<![\w.,-])(\d[\d,]*(?:\.\d+)?)-(?=\d[\d,]*(?:\.\d+)?\s?(?:" + _SIGN_AFTER + r"))")
# Figures written the continental way: a point between the thousands and a comma
# before the decimals ("1.299,50"). Without the points a comma is a decimal
# comma only next to a currency or a percent sign ("€12,50", "0,99 €", "3,5%")
# or before a unit ("1,5 kg", see ``_decimal_comma``); "1,2 and 3" stays a list.
_CONTINENTAL = re.compile(r"(?<![\w.,])([1-9]\d{0,2}(?:\.\d{3})+),(\d{1,2})(?!\d|[.,]\d)")
_COMMA_AFTER_SIGN = re.compile(r"((?:[$£€¥₹]|(?<![A-Za-z])(?:" + _CURRENCY_CODES + r"))\s?-?\d+),(\d{1,2})(?!\d|[.,]\d)")
_COMMA_BEFORE_SIGN = re.compile(r"(?<![\w.,])(\d+),(\d{1,2})(?=\s?(?:%|" + _SIGN_AFTER + r"))")
# "$x = 2$", "$3 + 5 = 8$": the sign after the last figure closes a formula, it is
# not a currency written after an amount. A formula opens with a sign before a
# letter, or before a figure or a space when a "=" or the like follows; "from $5
# to 30$" is two prices, and the sign in "5 $, 10 $" opens nothing. The closing
# sign becomes a mark no rule knows, so the rest is read as it was before.
_FORMULA_SIGN = chr(0xE004)
_FORMULA_END = re.compile(r"(?<![\w$])(?<!\d\s)\$(?:(?=[^\s\d$.,;:!?)])[^$\n]{0,80}"
                          r"|(?=\d)[^$\n]{0,80}[=^_\\{}+*/<>][^$\n]{0,80}"
                          r"|(?=\s)[^$\n]{0,80}[=^_\\{}+*<>][^$\n]{0,80})\d\s?\$(?![\w$])")
_VULGAR = re.compile(r"(?<![\d.,/])(?:(\d+)\s?)?([½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅐⅛⅜⅝⅞⅑⅒])")
_ADDRESS = re.compile(
    r"(?P<url>(?:https?://|www\.)[^\s<>\"']+)"
    r"|(?P<mail>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"
    r"|(?P<file>(?<![\w@./-])(?P<folder>/?(?:[\w~-]+/)+)?(?P<stem>[\w-]+(?:\.[\w-]+)*)\.(?P<ending>[A-Za-z][A-Za-z0-9]{0,9})"
    r"(?![\w-])(?P<path>/[^\s<>\"']*)?)")
_DAY_RANGE = re.compile(r"\b(" + _DAY_PATTERN + "|" + _MONTH_PATTERN + r")\b(\.?)\s?[-–]\s?(" + _DAY_PATTERN + "|"
                        + _MONTH_PATTERN + r")\b(\.?)")
_RATIO = re.compile(r"(?<![\d:.,])(\d{1,3}):(\d{1,3}(?:,\d{3})+|\d+)(?![\d:]|[.,]\d)")
_CODE = re.compile(r"(?<![\w.,/-])(#)?([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)(?![\w-]|[.,]\d)")
_SLASHED = re.compile(r"(?<![\w.,/-])(\d+(?:/\d+){2,})(?![\w/]|[.,]\d)")
_GROUPED = re.compile(
    r"(?<![\w.,:/#+-])(?P<plus>\+)?(?:(?P<lead>[A-Z]{2}) )?"
    r"(?P<core>[A-Z0-9]*\d[A-Z0-9]*(?: [A-Z0-9]*\d[A-Z0-9]*)+)"
    r"(?(lead)(?: (?P<trail>[A-Z]{2})(?![\w]))?)"
    r"(?![\w]|[.,:/-]\d|\s?[%°])")
_GLUED = re.compile(r"(?<![\w'.])(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+(?![\w']|\.\d)")


# Words whose accent is the only sign of how they are read: without it "résumé" is "resume".
_ACCENT_DECIDES = {"résumé": "R EH1 Z AH0 M EY2", "resumé": "R EH1 Z AH0 M EY2", "exposé": "EH2 K S P OW0 Z EY1",
                   "rosé": "R OW0 Z EY1", "pâté": "P AA0 T EY1", "maté": "M AA1 T EY2", "saké": "S AA1 K EY2",
                   "lamé": "L AA0 M EY1"}
_ACCENTED = re.compile(r"\b(" + "|".join(_ACCENT_DECIDES) + r")(s?)\b", re.IGNORECASE)
_LETTER_FORMS = {"ß": "ss", "æ": "ae", "Æ": "Ae", "œ": "oe", "Œ": "Oe", "ø": "o", "Ø": "O", "đ": "d", "ł": "l", "Ł": "L"}


def _plain_letter(char):
    """An accented Latin letter without its accent ("café" is in the dictionary
    as "cafe"). Other characters are left alone."""
    if char.isascii() or not char.isalpha():
        return char
    if char in _LETTER_FORMS:
        return _LETTER_FORMS[char]
    base = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c))
    return base if base.isascii() and base.isalpha() else char


# ---- numbers as words ------------------------------------------------------

def cardinal(number):
    """``1234`` -> ``"one thousand two hundred thirty four"``."""
    if number < 0:
        return "minus " + cardinal(-number)
    if number < 20:
        return _ONES[number]
    if number < 100:
        tens, ones = divmod(number, 10)
        return _TENS[tens - 2] + (" " + _ONES[ones] if ones else "")
    if number < 1000:
        hundreds, rest = divmod(number, 100)
        return _ONES[hundreds] + " hundred" + (" " + cardinal(rest) if rest else "")
    if number >= 1000 ** (len(_SCALES) + 1):
        return digits(str(number))
    parts = []
    for power in range(len(_SCALES), 0, -1):
        count, number = divmod(number, 1000 ** power)
        if count:
            parts.append(cardinal(count) + " " + _SCALES[power - 1])
    if number:
        parts.append(cardinal(number))
    return " ".join(parts)


def ordinal(number):
    words = cardinal(number).split()
    last = words[-1]
    words[-1] = _ORDINAL.get(last) or (last[:-1] + "ieth" if last.endswith("y") else last + "th")
    return " ".join(words)


def digits(text, zero="zero"):
    return " ".join(zero if c == "0" else _ONES[int(c)] for c in text if c.isdigit())


def year(number):
    """The way a year is said: 1984, 1905, 1900, 2005, 2026."""
    if not 1000 <= number <= 2999:
        return cardinal(number)
    high, low = divmod(number, 100)
    if low == 0:
        return cardinal(number) if high % 10 == 0 else cardinal(high) + " hundred"
    if high == 20 and low < 10:
        return "two thousand " + _ONES[low]
    return cardinal(high) + (" oh " + _ONES[low] if low < 10 else " " + cardinal(low))


def pairs(number):
    """A number read two digits at a time, the way model numbers are: 4070
    "forty seventy", 9001 "ninety oh one", 720 "seven twenty"."""
    high, low = divmod(number, 100)
    if not 100 <= number <= 9999 or (low == 0 and (high < 10 or high % 10 == 0)):
        return cardinal(number)
    if low == 0:
        return cardinal(high) + " hundred"
    return cardinal(high) + (" oh " + _ONES[low] if low < 10 else " " + cardinal(low))


def number_words(text):
    """An unsigned number as written: ``1,234``, ``3.14``, ``007``."""
    whole, _, fraction = text.replace(",", "").partition(".")
    if fraction:
        return (cardinal(int(whole)) if whole else "") + " point " + digits(fraction)
    if len(whole) > 1 and whole.startswith("0") or len(whole) > 18:
        return digits(whole)
    return cardinal(int(whole))


def duration(hours, minutes, seconds):
    """``2:03:45`` as a length of time: "two hours, three minutes and forty five seconds"."""
    parts = [f"{cardinal(count)} {name if count == 1 else name + 's'}"
             for count, name in ((hours, "hour"), (minutes, "minute"), (seconds, "second")) if count]
    if len(parts) < 2:
        return parts[0] if parts else "zero seconds"
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _plural_of(words):
    """Plural of a spelled number, for decades: "nineteen nineties"."""
    head, _, last = words.rpartition(" ")
    last = last[:-1] + "ies" if last.endswith("y") else last + "s"
    return (head + " " if head else "") + last


def _fraction_words(top, bottom, article=False):
    """"three quarters", "one half"; after a whole number "a half", "an eighth"."""
    one, many = _FRACTION.get(bottom, (ordinal(bottom), ordinal(bottom) + "s"))
    if top != 1:
        return f"{cardinal(top)} {many}"
    return (("an " if one[0] in "aeiou" else "a ") if article else "one ") + one


def _version_part(part):
    """One part of a version number: "4" four, "12" twelve, "03" zero three, "129" one two nine."""
    return digits(part) if len(part) > 2 else number_words(part)


def _minor(part):
    """The part after the point of a version: "12" twelve, "04" oh four."""
    return digits(part, "oh") if part.startswith("0") else cardinal(int(part))


def _short_number(text):
    """A number in a code that is said as a number: one or two digits, or a round one (B-12, KX-300)."""
    if text.startswith("0"):
        return False
    return len(text) <= 2 or set(text[1:]) == {"0"}


def _spelled(letters):
    return f"{_SPELL}{letters}{_END}"


def _before(text, position, count=4):
    """The words just before ``position`` in the same clause, in lower case."""
    clause = re.split(r"[.!?;…]\s|[()\"]", text[max(0, position - 80):position])[-1]
    return [word.lower() for word in re.findall(r"[A-Za-z]+", clause)][-count:]


def _identifier(text, position):
    """What the words before a number say it is: ``"phone"``, ``"pin"``,
    ``"strong"`` (a number, an ID, a reference), ``"weak"`` (an order, a
    ticket), ``"enter"`` or ``None``."""
    words = _before(text, position)
    if not words:
        return None
    if words[-1] in _PHONE_WORDS or (words[-1] in _PHONE_LINKS and any(word in _PHONE_WORDS for word in words[-3:-1])):
        return "phone"
    index = len(words) - 1
    while index > 0 and words[index] in _LINK_WORDS:
        index -= 1
    for kind, group in (("phone", _PHONE_WORDS), ("pin", _PIN_WORDS), ("strong", _STRONG_WORDS), ("weak", _WEAK_WORDS)):
        if words[index] in group:
            return kind
    return "enter" if words[-1] == "enter" else None


def _decimal_comma(text):
    """"1,5" before a unit is one number: a comma with one or two digits after
    it does not part thousands. "1,250" is left as it is."""
    return text.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", text) else text


def _address_digits(text):
    """Digits inside a file name or an address: 3, 2026, 0412."""
    if len(text) <= 2 and not (len(text) == 2 and text[0] == "0"):
        return cardinal(int(text))
    if len(text) == 4 and 1900 <= int(text) <= 2099:
        return year(int(text))
    return digits(text)


# ---- rewriting -------------------------------------------------------------

class Normalizer:
    def __init__(self, is_word=None):
        self.is_word = is_word or (lambda word: True)
        self.abbreviations = {columns[0]: (columns[1], columns[2]) for _, columns in tables.rows("abbreviations.txt")}
        # A unit marked "exact" is written in one letter case only: "m" is a meter, "M" is not.
        self.units, self.exact_units = {}, {}
        for _, columns in tables.rows("units.txt"):
            if len(columns) > 3 and columns[3] == "exact":
                self.exact_units[columns[0]] = (columns[1], columns[2])
            else:
                self.units[columns[0].lower()] = (columns[1], columns[2])
        # A chat spelling marked "alone" is read that way only as a reply by itself ("k", "k, thanks").
        self.chat, self.replies = {}, set()
        for number, columns in tables.rows("chat.txt"):
            if len(columns) > 2 and columns[2:] != ["alone"]:
                raise ValueError(f"chat.txt line {number}: after the words to say there can only be \"alone\"")
            self.chat[columns[0]] = columns[1] if len(columns) > 1 else "-"
            if len(columns) > 2:
                self.replies.add(columns[0])
        self.endings = tables.mapping("endings.txt")
        names = sorted({re.escape(unit) for unit in list(self.units) + list(self.exact_units)}, key=lambda name: (-len(name), name))
        self._unit_names = "|".join(names)
        self._unit = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?:[-–](\d[\d,]*(?:\.\d+)?))?\s?(" + self._unit_names
                                + r")(?![A-Za-z])(\.(?=\s+(?-i:[a-z])))?", re.IGNORECASE)
        self._area = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s?(km|cm|mm|m|ft|mi|yd|in)([²³])")
        self._area_plain = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s?(km|cm|mm|m|ft)([23])(?![\w])")
        self.inline = []
        self.day_first = False
        self.dated = False

    # -- pieces of the text that are not words --

    def _amount(self, symbol, whole, fraction, scale):
        one, many, cent, cents = _CURRENCY[symbol]
        if scale:
            scale = _SCALE_LETTER.get(scale.lower(), scale.lower())
            return f"{number_words(whole + ('.' + fraction if fraction else ''))} {scale} {many}"
        if fraction and (len(fraction) > 2 or not cent):
            return f"{number_words(whole + '.' + fraction)} {many}"
        amount, change = int(whole), int((fraction or "0").ljust(2, "0"))
        parts = []
        if amount or not change:
            parts.append(f"{cardinal(amount)} {one if amount == 1 else many}")
        if change and cent:
            parts.append(f"{cardinal(change)} {cent if change == 1 else cents}")
        return " and ".join(parts)

    @staticmethod
    def _continental(match):
        """"1.299,50" as "1,299.50". Four groups that could be an internet address are left alone."""
        groups = match.group(1).split(".")
        if len(groups) == 4 and all(int(group) <= 255 for group in groups):
            return match.group(0)
        return ",".join(groups) + "." + match.group(2)

    def _money(self, match):
        found = match.groupdict()
        whole = found["whole"].replace(",", "").replace(" ", "")
        words = self._amount(found["symbol"], whole, found["fraction"], found.get("scale"))
        return (" minus " if found.get("minus") or found.get("inner") else " ") + words + " "

    @staticmethod
    def _half_day(match, dotted, plain):
        """" A M" or " P M" as letters. A full stop that closes "p.m." is kept
        as a sentence end only when a new sentence follows."""
        if not (dotted or plain):
            return ""
        following = match.string[match.end():].lstrip()
        first = re.match(r"[A-Za-z']+", following)
        closes = bool(dotted) and match.group(0).endswith(".") and (
            not following or (following[0].isupper() and first is not None and first.group(0).lower() in _SENTENCE_STARTERS))
        return f"{_SPELL}{(dotted or plain).upper()}M{_END}{' .' if closes else ''} "

    def _time(self, match):
        hour, minute, second = int(match.group(1)), int(match.group(2)), match.group(3)
        half = match.group(4) or match.group(5)
        before = _before(match.string, match.start(), 3)
        if second is not None and not half and not (before and before[-1] == "at"):
            return f" {duration(hour, minute, int(second))} "               # 2:03:45 is a length of time
        if hour > 24 and second is None and not half:
            after = re.match(r"\s*([A-Za-z]+)", match.string[match.end():])
            if set(before) & _DURATION_WORDS or (after and after.group(1).lower() in _DURATION_WORDS):
                return f" {duration(0, hour, minute)} "                     # 48:12 long
            return f" {cardinal(hour)} {'oh ' if minute < 10 else ''}{cardinal(minute)} "
        if hour > 24:
            return match.group(0)
        words = cardinal(hour)
        if minute == 0:
            if half:
                pass
            elif hour == 0:
                words = "midnight"
            elif hour > 12:
                words += " hundred"                                         # 20:00
            else:
                words += " o'clock"
        else:
            words += (" oh " if minute < 10 else " ") + cardinal(minute)
        if second:
            words += " and " + cardinal(int(second)) + (" second" if int(second) == 1 else " seconds")
        return f" {words} " + self._half_day(match, match.group(4), match.group(5))

    def _dot_times(self, match):
        """"9.30 to 11.30" where the words before say it is a time of day."""
        following = match.string[match.end():]
        if int(match.group(1)) > 23 or int(match.group(4)) > 23 or not set(_before(match.string, match.start())) & _CLOCK_WORDS \
                or re.match(r"\s?(?:%|percent|million|billion|" + self._unit_names + r")(?![A-Za-z])", following, re.IGNORECASE):
            return match.group(0)
        return f"{match.group(1)}:{match.group(2)}{match.group(3)}{match.group(4)}:{match.group(5)}"

    def _ratio(self, match):
        """16:9, 3:1, 1:25,000. Two digits after the colon are a time unless the words say "ratio"."""
        first, second = match.group(1), match.group(2)
        if len(first) <= 2 and len(second) == 2 and second[0] in "012345":
            after = re.match(r"\s*([A-Za-z]+)", match.string[match.end():])
            if not (set(_before(match.string, match.start(), 3)) & _RATIO_WORDS
                    or (after and after.group(1).lower() in _RATIO_WORDS)):
                return match.group(0)
        return f" {number_words(first)} to {number_words(second)} "

    def _date(self, month, day, year_text=None, the=False):
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            return None
        words = f"the {ordinal(day)} of {_MONTHS[month - 1]}" if the else f"{_MONTHS[month - 1]} {ordinal(day)}"
        if year_text:
            words += " " + (year(int(year_text)) if len(year_text) == 4 else ("oh " if int(year_text) < 10 else "") + cardinal(int(year_text)))
        return f" {words} "

    def _slash_date(self, match):
        first, second = int(match.group(1)), int(match.group(2))
        if first > 12 >= second or (self.day_first and second <= 12):
            first, second = second, first                  # day first
        return self._date(first, second, match.group(3)) or match.group(0)

    def _dot_date(self, match):
        """15.11.2026: dates written with full stops put the day first."""
        day, month = int(match.group(1)), int(match.group(2))
        if month > 12 >= day:
            day, month = month, day
        return self._date(month, day, match.group(3)) or match.group(0)

    def _day_month(self, match):
        """"22 February", "5 Jan. 2026". The stop after a short month name is dropped; any other one ends the sentence."""
        month = match.group(2)
        spoken = self._date(_MONTH_NUMBER[month.lower()[:3]], int(match.group(1)), match.group(4), the=True)
        if spoken is None:
            return match.group(0)
        return spoken + (". " if match.group(3) and month in _MONTHS else "")

    def _days_of_month(self, match):
        """"3-17 November" and "November 3-17"."""
        month_first = match.group(1)[0].isalpha()
        month, first, second = (match.group(1), match.group(2), match.group(3)) if month_first else \
            (match.group(3), match.group(1), match.group(2))
        first, second = int(first), int(second)
        if not (1 <= first <= 31 and 1 <= second <= 31):
            return match.group(0)
        name = _MONTHS[_MONTH_NUMBER[month.lower()[:3]] - 1]
        words = f"{name} {ordinal(first)} to {ordinal(second)}" if month_first else \
            f"the {ordinal(first)} to the {ordinal(second)} of {name}"
        return f" {words}{' ' + year(int(match.group(4))) if match.group(4) else ''} "

    def _day_range(self, match):
        """"Mon.-Fri.", "Jan-Mar": from one day or month to another."""
        names = []
        for name in (match.group(1), match.group(3)):
            key = name.lower()
            names.append(self.abbreviations[key][1] if key in self.abbreviations else _DAY_NAMES.get(key, name))
        following = match.string[match.end():].lstrip()
        first = re.match(r"[A-Za-z']+", following)
        ends = bool(match.group(4)) and (not following or (following[0].isupper() and first is not None
                                                           and first.group(0).lower() in _SENTENCE_STARTERS))
        return f"{names[0]} to {names[1]}{' .' if ends else ''}"

    def _short_date(self, match):
        """"14/03", "12/10" as a day of the year, or ``None`` when it is a fraction."""
        first_text, second_text = match.group(1), match.group(2)
        if len(first_text) > 2 or len(second_text) > 2:
            return None
        first, second = int(first_text), int(second_text)
        before = _before(match.string, match.start())
        if 1 <= first <= 12 and 20 <= second <= 49 and "card" in before:
            return f" {_MONTHS[first - 1]} {year(2000 + second)} "       # a card that expires 08/27
        last = before[-1] if before else ""
        classic = first < second and second in _CLASSIC_FRACTIONS      # 1/2, 3/4, 7/10
        zero = len(first_text) == 2 and first_text[0] == "0" or len(second_text) == 2 and second_text[0] == "0"
        if not (zero or (12 < first <= 31 and second <= 12 and (first, second) != (24, 7))
                or (last in _DATE_BEFORE and (not classic or last == "on"))
                or (self.dated and not classic and first != second)):
            return None
        if first > 12 or (self.day_first and second <= 12):
            first, second = second, first                  # day first
        return self._date(first, second)

    def _fraction(self, match):
        spoken = self._short_date(match)
        if spoken:
            return spoken
        top, bottom = int(match.group(1)), int(match.group(2))
        if (top, bottom) == (24, 7) or top == bottom:
            return f" {cardinal(top)} {cardinal(bottom)} "         # twenty four seven, fifty fifty
        if not 0 < top < 100 or not 1 < bottom <= 100:
            return f" {cardinal(top)} over {cardinal(bottom)} "
        return f" {_fraction_words(top, bottom)} "

    def _mixed_fraction(self, match):
        """"2 1/2": two and a half."""
        top, bottom = int(match.group(2)), int(match.group(3))
        if not 0 < top < bottom:
            return match.group(0)
        return f" {number_words(match.group(1))} and {_fraction_words(top, bottom, article=True)} "

    def _vulgar(self, match):
        """"½" and "1½". Runs before the text is normalised, which would turn "1½" into "11/2"."""
        top, bottom = (int(part) for part in unicodedata.normalize("NFKC", match.group(2)).split("⁄"))
        if match.group(1) is None:
            return f" {top}/{bottom} "
        return f" {cardinal(int(match.group(1)))} and {_fraction_words(top, bottom, article=True)} "

    def _phone(self, match):
        groups = [g for g in match.groups() if g]
        return " " + ", ".join("eight hundred" if g == "800" else digits(g, "oh") for g in groups) + " "

    def _measure(self, match):
        unit = match.group(3)
        names = self.exact_units.get(unit) or self.units.get(unit.lower())
        if names is None or (len(unit) == 1 and match.string[match.end(3):match.end(3) + 1] in ("-", "'", "/")):
            return match.group(0)
        one, many = names
        value, upper = _decimal_comma(match.group(1)), match.group(2) and _decimal_comma(match.group(2))
        if upper:
            return f" {number_words(value)} to {number_words(upper)} {many} "
        return f" {number_words(value)} {one if value in ('1', '1.0') else many} "

    def _square(self, match):
        """"120 m²", "3 m3": square and cubic measures."""
        unit = match.group(2)
        one, many = {"in": ("inch", "inches")}.get(unit) or self.exact_units.get(unit) or self.units[unit]
        kind = "square" if match.group(3) in "²2" else "cubic"
        value = _decimal_comma(match.group(1))
        return f" {number_words(value)} {kind} {one if value in ('1', '1.0') else many} "

    def _counted(self, text, end):
        """True when a plural noun follows a number: it is then an amount, not a reference."""
        after = re.match(r"\s*([A-Za-z]+)", text[end:])
        if not after:
            return False
        word = after.group(1).lower()
        if word in ("people", "men", "women", "children", "feet", "miles"):
            return True
        return len(word) > 3 and word.endswith("s") and not word.endswith("ss") and word not in _NOT_COUNTED \
            and self.is_word(word[:-1])

    def _number(self, match, text):
        value = match.group(0)
        plain = value.replace(",", "")
        if "." not in plain and "," not in value and not plain.startswith("0") and len(plain) > 2:
            kind = _identifier(text, match.start())
            limit = {"phone": 3, "pin": 3, "strong": 4, "enter": 4, "weak": 5}.get(kind, 7)
            if len(plain) >= limit and not (kind is None and plain.endswith("000")) \
                    and not (kind == "enter" and len(plain) == 4 and 1900 <= int(plain) <= 2099) \
                    and not (kind in (None, "phone", "weak") and self._counted(text, match.end())):
                return f" {digits(plain, 'oh' if kind == 'phone' else 'zero')} "     # a reference, not an amount
        if "." not in plain and "," not in value and len(plain) == 4 and not plain.startswith("0"):
            number = int(plain)
            before = re.findall(r"[A-Za-z]+", text[:match.start()][-24:])
            after = re.match(r"\s*([A-Za-z]+)", text[match.end():])
            counted = bool(after) and re.search(r"(?:[^s]s|people|men|women|children|feet|miles)$", after.group(1).lower()) is not None
            dated = bool(before) and (before[-1].lower() in _YEAR_CONTEXT or before[-1].lower()[:3] in _MONTH_NUMBER)
            model = re.search(r"(?<![A-Za-z])([A-Z]{2,5}) $", text[:match.start()])
            if model and model.group(1) not in _CAPITAL_WORDS and not counted:
                return f" {pairs(number)} "                                 # RTX 4070, ISO 9001
            if 1100 <= number <= 1999 or (2000 <= number <= 2099 and (dated or not counted)):
                return f" {year(number)} "
        return f" {number_words(value)} "

    # -- codes and reference numbers --

    def _reads_as_word(self, letters):
        """Letters inside a code that are a word to say, not letters to name: SAVE-20."""
        lower = letters.lower()
        if len(lower) < 3 or not self.is_word(lower):
            return False
        return len(lower) > 3 or any(self.is_word(lower + ending) for ending in ("s", "es", "ed", "ing"))

    @staticmethod
    def _alnum(group, zero="zero"):
        """A group that mixes letters and digits: the letters are named, the digits read one by one."""
        return " ".join(digits(run, zero) if run.isdigit() else _spelled(run) for run in re.findall(r"[A-Za-z]+|\d+", group))

    @staticmethod
    def _digit_groups(groups, zero="zero"):
        """Groups of digits with a short break between them. Small numbers stay numbers: 9-1-1."""
        if all(_short_number(group) and len(group) <= 2 for group in groups):
            return " , ".join(cardinal(int(group)) for group in groups)
        return " , ".join(digits(group, zero) for group in groups)

    def _code_words(self, groups, match):
        token = "-".join(groups)
        if not any(char.isdigit() for char in token):
            return None                                            # well-known, Wi-Fi
        kinds = ["d" if g.isdigit() else "m" if any(c.isdigit() for c in g) else "u" if g.isupper() else "l" for g in groups]
        if all(kind == "d" for kind in kinds):
            if len(groups) == 2:
                years = all(len(g) == 4 and 1000 <= int(g) <= 2100 for g in groups)
                if not (match.group(1) or any(len(g) > 1 and g[0] == "0" for g in groups)
                        or (min(len(g) for g in groups) >= 4 and not years)
                        or _identifier(match.string, match.start()) in ("strong", "pin")):
                    return None                                    # 10-15 and 2019-2021 are ranges
            return self._digit_groups(groups)
        if len(groups) == 2 and kinds[1] == "d" and kinds[0] in "ul":
            letters, number = groups
            if (kinds[0] == "l" and len(letters) > 1) or self._reads_as_word(letters):
                return None                                        # pre-2020, COVID-19, SAVE-20
            if _short_number(number):
                return f"{_spelled(letters)} {cardinal(int(number))}"      # B-12, KX-300
            return f"{_spelled(letters)} , {digits(number)}"
        if len(groups) == 2 and kinds[0] == "d" and (kinds[1] == "l" or len(groups[1]) == 1
                                                     or re.fullmatch(r"\d+[A-Za-z]+", groups[1])):
            return None                                            # 5-year, 3-D, 5-10MB
        if any((kind == "l" and len(g) > 2) or (kind == "m" and re.fullmatch(r"\d+(?:s|st|nd|rd|th)", g))
               for kind, g in zip(kinds, groups)):
            return None                                            # 20-year-old, F-16s
        if not any(char.isupper() for char in token) and ("l" in kinds or any(kind == "m" for kind in kinds)):
            return None                                            # 3-in-1, 50s-60s
        parts = []
        for kind, group in zip(kinds, groups):
            if kind == "d":
                parts.append(digits(group))
            elif kind == "m":
                parts.append(self._alnum(group))
            elif len(group) > 3 and self.is_word(group.lower()):
                parts.append(group)
            else:
                parts.append(_spelled(group) if len(group) <= 5 else group)
        return " , ".join(parts)

    def _code(self, match):
        """Codes written with hyphens: AB-4471-Z, 91-220-0017, #A7-4419."""
        words = self._code_words(match.group(2).split("-"), match)
        if words is None:
            return match.group(0)
        return (" number " if match.group(1) else " ") + words + " "

    def _grouped(self, match):
        """Digits written in groups with spaces: a telephone number, a card or
        tracking number, or a large number with spaces between the thousands."""
        text, plus, lead, trail = match.string, match.group("plus"), match.group("lead"), match.group("trail")
        core = match.group("core").split(" ")
        head = tail = ""
        if lead in _CAPITAL_WORDS:                                 # "IN 2019 150 ..." in capitals
            head, tail, lead, trail = lead + " ", (" " + trail if trail else ""), None, None
        kind = _identifier(text, match.start())
        pure = all(part.isdigit() for part in core)
        if pure and not plus and not lead:
            following = text[match.end():]
            amount = self._counted(text, match.end()) or re.match(r"\s?(?:" + self._unit_names + r")(?![A-Za-z])", following,
                                                                  re.IGNORECASE) is not None
            if kind is None and core[0][0] != "0" and len(core[0]) <= 3 and all(len(part) == 3 for part in core[1:]) \
                    and (core[-1] == "000" or (amount and len(core) > 2)):
                return head + ",".join(core) + tail                # 1 000 000: the number rules read it
            if not (kind or (len(core[0]) > 1 and core[0][0] == "0") or (len(core) > 2 and any(len(part) > 2 for part in core))):
                return match.group(0)
        elif not pure and not lead and not plus and kind is None:
            return match.group(0)
        zero = "oh" if plus or kind == "phone" or (pure and core[0][0] == "0" and sum(len(part) for part in core) >= 10) else "zero"
        if pure:
            spoken = self._digit_groups(core, zero)
        else:
            spoken = " , ".join(digits(part, zero) if part.isdigit() else self._alnum(part, zero) for part in core)
        if lead:
            spoken = f"{_spelled(lead)} , {spoken}"
        if trail:
            spoken = f"{spoken} , {_spelled(trail)}"
        return head + (" plus " if plus else " ") + spoken + " " + tail

    def _glued(self, match):
        """Letters and digits written together: B12, 14C, X7K, PS5. A single
        letter is always named; it is never the article "a"."""
        out = []
        for run in re.findall(r"[A-Za-z]+|\d+", match.group(0)):
            if run.isdigit():
                out.append(cardinal(int(run)) if _short_number(run) else digits(run))
            elif len(run) == 1 or ((run.isupper() or len(run) <= 3) and not self._reads_as_word(run)):
                out.append(_spelled(run))
            else:
                out.append(run)
        return " " + " ".join(out) + " "

    # -- web addresses and file names --

    def _address_part(self, part):
        """One run of letters inside an address: a word, or letters to name."""
        lower = part.lower()
        if len(part) > 1 and self.is_word(lower) and (len(part) > 2 or lower in _SHORT_WORDS):
            return part
        return _spelled(part) if len(part) <= 3 else part

    def _spoken_address(self, core):
        pieces = re.findall(r"[A-Za-z]+|\d+|.", core)
        mail, host = "@" in core, False
        out = []
        for index, piece in enumerate(pieces):
            following = pieces[index + 1] if index + 1 < len(pieces) else ""
            if piece == "@":
                host = True
            if piece.isdigit():
                out.append(_address_digits(piece))
            elif not piece.isalpha():
                out.append(_SEPARATORS.get(piece, ""))
            elif index and pieces[index - 1] == "." and (host or not mail) and (
                    following in ("", "/", ":", "?", "#")
                    or (len(piece) <= 3 and (piece.lower() in self.endings or not self.is_word(piece.lower())))):
                # the ending of a file name or an address: a word if the table says so, otherwise letters
                out.append(piece.lower() if self.endings.get(piece.lower()) == "word" else _spelled(piece))
            else:
                letters = ""
                for part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", piece):
                    spoken = self._address_part(part)
                    if spoken.startswith(_SPELL):
                        letters += part
                        continue
                    if letters:
                        out.append(_spelled(letters))
                        letters = ""
                    out.append(spoken)
                if letters:
                    out.append(_spelled(letters))
        return " ".join(item for item in out if item)

    def _address(self, match):
        """Web and mail addresses, file names and paths: the dots, slashes,
        underscores and @ are spoken. The ending is a word when
        ``data/endings.txt`` says so ("dot com") and letters otherwise ("dot
        P D F")."""
        whole = match.group(0)
        text = whole.rstrip(".,;:!?)")                     # punctuation of the sentence, not of the address
        tail = whole[len(text):]
        if match.group("file"):
            ending = match.group("ending")
            known = ending.lower() in self.endings
            marked = bool(match.group("folder") or match.group("path")) or "_" in match.group("stem")
            if not (known or (marked and len(ending) <= 5 and (ending.islower() or ending.isupper())
                              and not self.is_word(ending.lower()))):
                return whole                               # "the end.Then": a missing space, not a file
        core = re.sub(r"^(?:https?://)?(?:www\.)?", "", text).rstrip("/")
        return f" {self._spoken_address(core)} {tail}"

    def _chat_form(self, match):
        """Chat spellings that contain a digit or a slash: gr8, b4, 2day."""
        said = self.chat.get(match.group(0).lower())
        if said is None:
            return match.group(0)
        if said == "-":
            return " "
        return " " + " ".join(f"{_SPELL}{part[1:]}{_END}" if part.startswith("*") else part for part in said.split()) + " "

    def _inline(self, match):
        """``{...}``: a pronunciation written by the user. Braces that hold
        anything else are no error: they stay and are read like brackets
        ("{name}", "{1, 2, 3}", "\\frac{1}{2}"). So are single letters, which
        are phones only by chance ("x_{i}", "{n}")."""
        symbols = match.group(2).split()
        if not symbols or all(len(symbol) == 1 and symbol.isascii() for symbol in symbols):
            return match.group(0)
        try:
            phones = convert("", symbols) if is_arpabet(symbols) else from_text(" ".join(symbols))
        except ValueError:
            return match.group(0)
        self.inline.append((match.group(1) or "", phones))
        return f" {_INLINE}{chr(_INLINE_BASE + len(self.inline) - 1)}{_INLINE} "

    def _dotted(self, match, text):
        """``U.S.``, ``e.g.``, ``p.m.``: letters with full stops."""
        letters = match.group(0).replace(".", "")
        key = letters.lower()
        following = text[match.end():].lstrip()
        if key == "eg":
            words = "for example"
        elif key == "ie":
            words = "that is"
        else:
            words = f"{_SPELL}{letters.upper()}{_END}"
        first = re.match(r"[A-Za-z']+", following)
        ends_sentence = not following or (following[0].isupper() and first and first.group(0).lower() in _SENTENCE_STARTERS)
        return f" {words}{' .' if ends_sentence and match.group(0).endswith('.') else ''} "

    def _abbreviation(self, match, text):
        token, stop = match.group(1), match.group(2)
        key = token.lower()
        following = text[match.end():]
        next_word = re.match(r"\s*([A-Za-z]+|\d)", following)
        capital_next = bool(next_word) and next_word.group(1)[0].isupper()
        capital_before = re.search(r"[A-Z][a-z]+\s+$", text[:match.start()]) is not None
        if key in ("st", "dr") and token[0].isupper():
            if capital_next and (stop or key == "dr"):
                return (" saint " if key == "st" else " doctor ")
            if capital_before and stop:
                return (" street" if key == "st" else " drive") + (" ." if not following.strip() else " ")
            return match.group(0)
        if key not in self.abbreviations:
            return match.group(0)
        when, words = self.abbreviations[key]
        number_next = bool(next_word) and next_word.group(1).isdigit()
        if when == "title":
            if not (token[0].isupper() and (capital_next or stop)):
                return match.group(0)
        elif when == "number":
            previous = re.search(r"([A-Za-z]+)\.?\s+$", text[:match.start()])
            if not (stop and (number_next or (key == "no" and previous and previous.group(1).lower() in _NUMBERED))):
                return match.group(0)
        elif not stop or (when == "small" and token.isupper()):
            return match.group(0)
        elif key in ("mar", "sun", "sat", "jan", "dec", "max", "min", "est", "no") and not token[0].isupper() and not number_next:
            # also words; "max. load" and "est. time" are the abbreviation, "he sat." is not
            if not (key in ("max", "min", "est") and next_word and next_word.group(1)[0].islower()):
                return match.group(0)
        if key == "est" and not number_next:
            words = "estimated"                            # "Est. arrival"; "est. 1885" is "established"
        ends_sentence = when != "title" and (not following.strip() or (capital_next and next_word.group(1).lower() in _SENTENCE_STARTERS))
        return f" {words}{' .' if ends_sentence else ''} "

    def rewrite(self, text):
        """The text with every non-word written out, markers included."""
        text = _VULGAR.sub(self._vulgar, text)             # before "1½" becomes "11/2" and "m²" becomes "m2"
        text = self._area.sub(self._square, text)
        text = text.replace("²", " squared ").replace("³", " cubed ")
        text = unicodedata.normalize("NFKC", text).replace("⁄", "/").replace("−", " minus ")
        if not text.isascii():
            text = _ACCENTED.sub(lambda m: "{" + _ACCENT_DECIDES[m.group(1).lower()] + (" Z" if m.group(2) else "") + "}", text)
            text = "".join(_plain_letter(char) for char in text)
        text = re.sub(r"(?<=\d)–(?=\d)", "-", text)        # 10–15 is a range, not a pause
        text = _DAY_RANGE.sub(self._day_range, text)
        for old, new in (("‘", "'"), ("’", "'"), ("‚", "'"), ("‛", "'"), ("`", "'"), ("´", "'"), ("“", '"'), ("”", '"'),
                         ("„", '"'), ("‟", '"'), ("«", '"'), ("»", '"'), ("–", "—"), ("―", "—"), ("[", "("), ("]", ")")):
            text = text.replace(old, new)
        self.inline = []
        text = re.sub(r"([A-Za-z']+)?\{([^{}]*)\}", self._inline, text)
        text = text.replace("{", "(").replace("}", ")")
        text = _ADDRESS.sub(self._address, text)
        text = text.replace("→", " to ")
        text = _EMOJI.sub(" ", text)
        text = _EMOTICON.sub(" ", text)
        text = re.sub(r"\.{3,}", "…", text)
        text = re.sub(r"(?<=\d)\s-\s(?=\d[\d.,]*\s?=)", " minus ", text)
        text = re.sub(r"(?<![\d.,/-])(\d[\d.,]*)-(?=\d[\d.,]*=)", r"\1 minus ", text)      # 10-3=7, not the date 2024-11-15=
        text = re.sub(r"-{2,}|\s-\s", "—", text)
        text = re.sub(r"\bw/o\b", " without ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bw/(?=\s|$)", " with ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bn/a\b", " not applicable ", text, flags=re.IGNORECASE)
        text = text.replace("'n'", " 'n ")
        if re.search(r"[<>≥≤≠]|!=", text):
            text = self._mark_comparisons(text)
        if re.search(r"\d", text):                          # most text has no digit and skips these passes
            text = self._figures(text)
        return self._signs(text)

    def _figures(self, text):
        """The passes that need a digit: money, times, dates, telephone numbers,
        versions, codes, units, fractions, ranges."""
        text = _FORMULA_END.sub(lambda match: match.group(0)[:-1] + _FORMULA_SIGN, text)
        # continental figures become American ones, so every rule below sees one notation
        text = _CONTINENTAL.sub(self._continental, text)
        text = _COMMA_AFTER_SIGN.sub(r"\1.\2", text)
        text = _COMMA_BEFORE_SIGN.sub(r"\1.\2", text)
        text = _MONEY.sub(self._money, text)
        text = _RANGE_BEFORE_SIGN.sub(r"\1 to ", text)                      # 5-10 €
        text = _MONEY_AFTER.sub(self._money, text)
        text = re.sub(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s?¢",
                      lambda m: f" {number_words(m.group(1))} {'cent' if m.group(1) == '1' else 'cents'} ", text)

        # times of day, lengths of time, ratios
        clock = r"\d{1,2}:[0-5]\d(?:\s?[AaPp]\.?[Mm]\.?)?|\b\d{1,2}\s?[AaPp]\.?[Mm]\.?"
        text = re.sub(r"(" + clock + r")\s(" + _ZONES + r")\b", lambda m: f"{m.group(1)} {_spelled(m.group(2))}", text)
        text = re.sub(r"(?<![\d.,:])(\d{1,2})\.([0-5]\d)(?=\s?[AaPp]\.?[Mm]\b)", r"\1:\2", text)          # 7.30 pm
        text = re.sub(r"(?<![\d.,:])(\d{1,2})\.(00|15|30|45)(\s?(?:to|until|till|and|[-—])\s?)(\d{1,2})\.(00|15|30|45)(?!\d|\.\d)",
                      self._dot_times, text)
        text = re.sub(r"(" + clock + r")\s?[-—]\s?(?=\d{1,2}(?::[0-5]\d|\s?[AaPp]\.?[Mm]\b))", r"\1 to ", text)
        text = _RATIO.sub(self._ratio, text)
        text = re.sub(r"(?<![\d:])(\d{1,2}):([0-5]\d)(?::([0-5]\d))?" + _HALF_DAY + r"?(?![\d:])", self._time, text)
        text = re.sub(r"(?<![\d.:,])(\d{1,2})" + _HALF_DAY + r"(?![A-Za-z])",
                      lambda m: f" {cardinal(int(m.group(1)))} " + self._half_day(m, m.group(2), m.group(3)), text)

        # dates
        seen = [(int(a), int(b)) for a, b in re.findall(r"(?<![\d/.])(\d{1,2})/(\d{1,2})(?:/(?:\d{4}|\d{2}))?(?![\d/])", text)]
        seen = [pair for pair in seen if pair != (24, 7)]
        self.day_first = any(a > 12 >= b for a, b in seen) and not any(b > 12 >= a for a, b in seen)
        self.dated = re.search(r"(?<![\d/])\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})(?![\d/])", text) is not None
        text = re.sub(r"(?<![\d-])(\d{4})-(\d{1,2})-(\d{1,2})(?![\d-])",
                      lambda m: self._date(int(m.group(2)), int(m.group(3)), m.group(1)) or m.group(0), text)
        text = re.sub(r"(?<![\d/])(\d{4})/(\d{1,2})/(\d{1,2})(?![\d/])",
                      lambda m: self._date(int(m.group(2)), int(m.group(3)), m.group(1)) or m.group(0), text)
        text = re.sub(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d|\.\d)", self._dot_date, text)
        text = re.sub(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?![\d/])", self._slash_date, text)
        text = re.sub(r"\b(" + _MONTH_PATTERN + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s?[-—]\s?(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?(?![\d:])",
                      self._days_of_month, text)
        text = re.sub(r"(?<![\d.,/:-])(\d{1,2})(?:st|nd|rd|th)?\s?[-—]\s?(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTH_PATTERN + r")\b(?:,?\s+(\d{4}))?",
                      self._days_of_month, text)
        text = re.sub(r"\b(" + _MONTH_PATTERN + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?(?![\d:])",
                      lambda m: self._date(_MONTH_NUMBER[m.group(1).lower()[:3]], int(m.group(2)), m.group(3)) or m.group(0), text)
        text = re.sub(r"(?<![\d.,/:-])(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTH_PATTERN + r")\b(\.(?=\s+[a-z\d]))?(?:,?\s+(\d{4}))?",
                      self._day_month, text)

        # telephone numbers, versions, codes
        text = re.sub(r"(?<![\d-])(?:\+?(1)[-.\s])?\(?(\d{3})\)?[-.\s](\d{3})[-.\s](\d{4})(?![\d-])", self._phone, text)
        text = re.sub(r"(?<![\w.,-])(\d{3})-(\d{4})(?![\w-])", self._phone, text)
        text = re.sub(r"(?<![\w.])([vV])?(\d+(?:\.\d+){2,})(?:-(\d+)(?![\w-]|\.\d))?(?![\w])",
                      lambda m: " " + (_spelled(m.group(1)) + " " if m.group(1) else "")
                      + " point ".join(_version_part(part) for part in m.group(2).split("."))
                      + (" dash " + number_words(m.group(3)) if m.group(3) else "") + " ", text)
        text = re.sub(r"(?<![\w.])([vV])(\d+)\.(\d{2,3})(?!\d|\.\d|\w)",
                      lambda m: f" {_spelled(m.group(1))} {cardinal(int(m.group(2)))} point {_minor(m.group(3))} ", text)
        text = re.sub(r"\b(" + _VERSIONED + r")(\.?\s(?:(?:from|to)\s)?)(\d+)\.(\d{2,3})(?:(\s(?:to|or|and)\s)(\d+)\.(\d{2,3}))?(?!\d|\.\d|\s?%|\s(?:percent|million|billion)\b)",
                      lambda m: f"{m.group(1)}{m.group(2)}{cardinal(int(m.group(3)))} point {_minor(m.group(4))}"
                      + (f"{m.group(5)}{cardinal(int(m.group(6)))} point {_minor(m.group(7))}" if m.group(5) else "") + " ",
                      text, flags=re.IGNORECASE)
        text = _CODE.sub(self._code, text)
        text = _SLASHED.sub(lambda m: " " + self._digit_groups(m.group(1).split("/")) + " ", text)
        text = _GROUPED.sub(self._grouped, text)

        text = re.sub(r"(?<![\w.])-(?=\d)", " minus ", text)
        text = re.sub(r"(?:(?<=\d)\s?[xX×]|×)\s?(?=\d[\d.,]*\s?(?:" + _LENGTHS + r")\b)", " by ", text)    # 3 × 4 metres
        text = re.sub(r"(?<=\d)\s[xX×]\s(?=\d)", " times ", text)
        text = re.sub(r"(?<![\w/'])[A-Za-z0-9/]*[0-9/][A-Za-z0-9/]*(?![\w/'])", self._chat_form, text)
        text = re.sub(r"(?<![\w.])'?(\d{2}|\d{4})'?s\b",
                      lambda m: " " + _plural_of(year(int(m.group(1))) if len(m.group(1)) == 4 else cardinal(int(m.group(1)))) + " ", text)
        text = re.sub(r"(?<![\w.])(\d+)(?:st|nd|rd|th)\b", lambda m: f" {ordinal(int(m.group(1)))} ", text)
        text = re.sub(r"(?<![\w.])(144|240|360|480|540|576|720|900|1080|1440|2160|4320)([pi])\b",
                      lambda m: f" {pairs(int(m.group(1)))} {_spelled(m.group(2))} ", text)                 # 1080p
        text = re.sub(r"(\d[\d,]*(?:\.\d+)?)\s?%", lambda m: f" {number_words(m.group(1))} percent ", text)
        text = self._area_plain.sub(self._square, text)
        text = self._unit.sub(self._measure, text)
        text = re.sub(r"(?<![\d/.,-])(\d+) (\d)/(2|3|4|5|6|8|10|16)(?![\d/]|\.\d)", self._mixed_fraction, text)
        text = re.sub(r"(?<![\d/.])(\d+)/(\d+)(?![\d/]|\.\d)", self._fraction, text)
        text = re.sub(r"(?<![\w.,-])(\d{4})[-–](\d{4})(?![\w.,-])", lambda m: f" {year(int(m.group(1)))} to {year(int(m.group(2)))} ", text)
        text = re.sub(r"(?<![\w.,-])(\d+)[-–](\d+)(?![\w-]|[.,]\d)", lambda m: f" {number_words(m.group(1))} to {number_words(m.group(2))} ", text)
        text = re.sub(r"(?<![\w.])(\d+)x\b", lambda m: f" {number_words(m.group(1))} times ", text)
        text = re.sub(r"(?<=\d)\^(?=\d)", " to the power of ", text)
        return text

    @staticmethod
    def _named_letters(text):
        """Mark the letters that stand for something, to be named: "a=10", "b>a", "(k)"."""
        if not any(sign in text for sign in "=<>+*/^()≤≥≠≈×÷±"):
            return text
        plain = _without_angles(text)
        places = {match.start("letter") for pattern in _LETTER_PLACES for match in pattern.finditer(plain)}
        if not places:
            return text
        return "".join(f"{_SPELL}{char.upper()}{_END}" if index in places else char for index, char in enumerate(text))

    @staticmethod
    def _mark_comparisons(text):
        """Put the mark for "is" after the first value of each comparison between
        two values: "67 > 66", "b>a", "f(x) >= 0". Not where a word that opens no
        clause stands before that value: "for n > 4", "any q > 0"."""
        plain = _without_angles(text)

        def mark(match):
            before, after = plain[:match.start()], plain[match.end():]
            value = _VALUE_BEFORE.search(before)
            if plain[match.start("sign")] != match.group("sign")[0] or value is None or not _VALUE_AFTER.match(after):
                return match.group(0)
            start = value.start()
            if value.group(0) in ")]":                      # "f(x) > 0", "a[i] < b": the whole of it is the value
                depth = 0
                while start >= 0:
                    depth += (before[start] in ")]") - (before[start] in "([")
                    if depth == 0:
                        break
                    start -= 1
                while start > 0 and (before[start - 1].isalnum() or before[start - 1] in "_."):
                    start -= 1
            word = re.search(r"[A-Za-z']+$", before[:max(start, 0)].rstrip())
            if word and word.group(0).lower() not in _CLAUSE_OPENERS:
                return match.group(0)
            return _IS + match.group(0)

        return _COMPARED.sub(mark, text)

    @staticmethod
    def _compared(match, words):
        """``words`` for a comparison sign, after "is" where the mark for it stands before the sign."""
        marked = match.group(0).startswith(_IS) or match.string[:match.start()].rstrip(" ").endswith(_IS)
        return f" {'is ' if marked else ''}{words} "

    def _joined_comparisons(self, text):
        """"b>a", "x<5", "p<.05": the words for "<" and ">" written with no spaces."""
        plain = _without_angles(text)

        def read(match):
            before, after = text[:match.start()].rstrip(_IS), text[match.end():]
            if plain[match.start()] != match.group(0):      # the bracket of a tag
                return match.group(0)
            if not (_FIGURE_BEFORE.search(before) or _FIGURE_AFTER.match(after)
                    or (_LETTER_BEFORE.search(before) and _LETTER_AFTER.match(after))):
                return match.group(0)
            return self._compared(match, "less than" if match.group(0) == "<" else "greater than")

        return _JOINED_COMPARISON.sub(read, text)

    def _signs(self, text):
        """The passes that follow: signs, abbreviations, and the numbers that are left."""
        text = self._named_letters(text)
        if "<" in text or ">" in text:
            text = self._joined_comparisons(text)
        text = re.sub(r"(?<![\w-])(" + _SIZES + r")-(" + _SIZES + r")(?![\w-])",
                      lambda m: f" {_spelled(m.group(1))} to {_spelled(m.group(2))} ", text)
        text = re.sub(r"#(?=\d)", " number ", text)
        text = re.sub(r"#(?=[A-Z]{1,4}-?\d)", " number ", text)                 # Order #A7
        text = re.sub(r"#(?=[A-Za-z])", " hashtag ", text)
        text = re.sub(r"~(?=\s?\d)", " about ", text)
        text = re.sub(r"(?<=[\w\s" + _END + _IS + r"])(>=|<=|!=)(?=[\w\s" + _SPELL + r"])",
                      lambda m: self._compared(m, _COMPARISONS[m.group(1)]), text)
        text = re.sub(r"(?<=\d) Ti\b", f" {_spelled('TI')}", text)              # RTX 4070 Ti
        text = re.sub(r"\b([Rr])ef\.\s?[Nn]o\.(?=\s)", r"\1eference number", text)
        text = re.sub(r"\b((?:[A-Za-z]\.){2,})", lambda m: self._dotted(m, text), text) if "." in text else text
        text = re.sub(r"\b([A-Za-z]{1,6})\b(\.?)(?![A-Za-z'’])", lambda m: self._abbreviation(m, text), text)
        if re.search(r"\d", text):
            text = _GLUED.sub(self._glued, text)
            text = re.sub(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|(?<![\w.])\.\d+", lambda m: self._number(m, text), text)
        text = re.sub(r"(?<=[A-Za-z])/(?=[A-Za-z])", " ", text)
        text = re.sub(r"(?<=\d)" + _IS + r"?\s?[<>]\s?(?=\d)|(?<=\s)[<>](?=\s)",
                      lambda m: self._compared(m, "less than" if "<" in m.group(0) else "greater than"), text)
        text = re.sub("[" + re.escape("".join(_SYMBOL_WORDS)) + "]",
                      lambda m: self._compared(m, _SYMBOL_WORDS[m.group(0)]) if m.group(0) in "≥≤≠" else f" {_SYMBOL_WORDS[m.group(0)]} ", text)
        return text.replace(_IS, "")

    # -- words --

    @staticmethod
    def _unstretched(word):
        """Spellings a word stretched for emphasis may stand for. A letter typed
        three times or more is cut to one or to two: at the end of a word one is
        the usual spelling ("sooo", "heyyy") unless the letter is one that
        doubles there ("alll", "offf"); inside a word two ("goood", "cooool").
        "mmm" is tried with two first: it is the hum "mm", not the letter M."""
        if not re.search(r"(.)\1\1", word):
            return []
        def cut(double_inside, double_final):
            def replace(match):
                final = match.end() == len(word)
                return match.group(1) * (2 if (double_final if final else double_inside) else 1)
            return re.sub(r"(.)\1{2,}", replace, word)
        liked = bool(re.search(r"([lfsz])\1\1+$", word)) or set(word) == {"m"} or re.sub(r"(.)\1{2,}$", r"\1", word) == "to"
        ordered = [cut(True, liked), cut(True, not liked), cut(False, liked), cut(False, not liked)]
        return list(dict.fromkeys(ordered))

    @staticmethod
    def _chat_words(chat, raw):
        """Tokens for one row of the chat table: words, letters to name, or nothing."""
        if chat == "-":
            return []
        return [Word(part[1:].lower(), raw=raw, spell=True) if part.startswith("*") else Word(part.lower(), raw=part)
                for part in chat.split()]

    @staticmethod
    def _reply(out, place):
        """True when the word at ``place`` is a clause by itself and can be a
        reply: "k", "k, thanks", "see you there, k?". Between two commas, or with
        a single letter next to it across a comma, it is one of a list: "i, j, k"."""
        marks = []
        for step in (-1, 1):
            index = place + step
            while 0 <= index < len(out) and isinstance(out[index], Punct) and out[index].mark in "\"'()":
                index += step                               # quotation marks and brackets part nothing
            if not 0 <= index < len(out):
                marks.append("")                            # the text starts or ends here
            elif isinstance(out[index], Word):
                return False                                # a word in the same clause: "the value of k"
            else:
                marks.append(out[index].mark)
                beyond = out[index + step] if 0 <= index + step < len(out) else None
                if out[index].mark == "," and isinstance(beyond, Word) and len(beyond.text) == 1 and beyond.text != "i":
                    return False
        return marks != [",", ","]

    def _word_tokens(self, raw, all_caps, previous, following=True, fresh=False):
        """Tokens for one run of letters and apostrophes as written. ``previous``
        is the word before it, ``following`` whether a word follows directly,
        ``fresh`` whether a new sentence starts here."""
        lower = raw.lower()
        chat = self.chat.get(lower)
        if chat is not None and (len(raw) > 1 or raw.islower()) and lower not in self.replies:
            return self._chat_words(chat, raw)
        if raw in _ROMAN and previous and previous[0].isupper():
            number = _ROMAN[raw]
            words = cardinal(number) if previous.lower() in _CARDINAL_AFTER else "the " + ordinal(number)
            return [Word(word, raw=raw) for word in words.split()]
        letters = raw.replace("'", "")
        possessive = lower.endswith("'s")
        stem = raw[:-2] if possessive else raw
        if len(stem) == 1 and stem.isalpha():
            # "A" is the article unless it labels something: "Plan A.", "vitamin A"
            label = stem == "A" and previous and (not following or (not fresh and previous.lower() in _LABELLED))
            if stem in ("a", "A", "I", "i") and not possessive and not label:
                return [Word(stem.lower(), raw=raw)]
            return [Word(lower, raw=raw, spell=True)]
        if len(stem) > 2 and stem[0] in "SsZz" and len(set(lower)) == 1 and (all_caps or not stem.isupper()):
            return [Word(lower, raw=raw, phones=((lower[0], 0),))]             # "Sss", "Zzzz": a hiss, a snore
        if stem.isupper() and stem.isalpha() and 2 <= len(stem) <= 5 and (not all_caps or not self.is_word(stem.lower())):
            if stem in _INITIALISMS or not self.is_word(stem.lower()):
                return [Word(lower, raw=raw, spell=True)]
        if not letters.isalpha():
            return []
        # iOS, macOS, eSIM: small letters, then capitals that are named. The dictionary's "ios" is another word.
        capitals = re.fullmatch(r"[a-z]+(?:[A-Z][a-z]+)*[A-Z]{2,}(?:'s)?", raw) is not None
        if capitals or not self.is_word(lower):
            for candidate in ([] if capitals else self._unstretched(lower)):      # "soooo" -> "so", "goooood" -> "good"
                if self.is_word(candidate):
                    return [Word(candidate, raw=raw)]
            parts = re.findall(r"[A-Z]?[a-z']+|[A-Z]+(?![a-z])", raw)
            if len(parts) > 1 and "".join(parts) == raw:               # iPhone, YouTube, JavaScript
                out = []
                for part in parts:
                    named = part in _INITIALISMS if capitals and part.isupper() else False
                    spelled = len(part) == 1 or named or (part.isupper() and not self.is_word(part.lower()))
                    if capitals and out and out[-1].spell and (spelled or part == "'s"):
                        out[-1] = out[-1]._replace(text=out[-1].text + part.lower(), raw=out[-1].raw + part)   # i + OS
                    else:
                        out.append(Word(part.lower(), attach=bool(out), raw=part, spell=spelled))
                return out
        return [Word(lower, raw=raw)]

    def tokens(self, text):
        text = self.rewrite(text)
        runs = re.findall(r"[A-Za-z]{2,}", text)
        all_caps = len(runs) >= 3 and sum(run.isupper() for run in runs) >= 0.6 * len(runs)
        out = []
        pattern = re.compile(
            _SPELL + r"([A-Za-z ]+)" + _END + r"|" + _INLINE + r"(.)" + _INLINE
            + r"|('?[A-Za-z]+(?:'[A-Za-z]+)*)|(\d+)|(-)|(\S)")
        attach = False
        previous = ""
        fresh = True                                       # a sentence starts here: "a plan. A dog" is the article
        short = []                                         # where "Ss" or "Zz" stands apart: perhaps a hiss, a snore
        replies = []                                       # where a chat spelling stands that is read only as a reply
        for match in pattern.finditer(text):
            spelled, inline, word, number, hyphen, other = match.groups()
            before = text[match.start() - 1] if match.start() else " "
            if hyphen:
                attach = bool(out) and isinstance(out[-1], Word) and not before.isspace() \
                    and match.end() < len(text) and text[match.end()].isalnum()
                continue
            new = []
            if spelled is not None:
                new = [Word(spelled.replace(" ", "").lower(), raw=spelled, spell=True)]
            elif inline is not None:
                written, phones = self.inline[ord(inline) - _INLINE_BASE]
                new = [Word(written.lower(), raw=written, phones=phones)]
            elif word is not None:
                if word.startswith("'") and word.lower() not in _LEADING_APOSTROPHE:
                    out.append(Punct("'"))
                    word = word[1:]
                elif word.startswith("'") and not self.is_word(word.lower()):
                    word = word[1:]
                new = self._word_tokens(word, all_caps, previous, re.match(r"\s*[A-Za-z]", text[match.end():]) is not None, fresh)
                previous = word
                if word in ("Ss", "ss", "Zz", "zz") and len(new) == 1 and (before.isspace() or before in "\"'(") \
                        and re.match(r"[.!?…,;:—\"')]*(?:\s|$)", text[match.end():]):
                    short.append(len(out))
                # a reply stands free: not "(k)", "/k/", "[:k]", and not before a colon or a mid-text "!" ("k: king", "k! = mk")
                if word.lower() in self.replies and (len(word) > 1 or word.islower()) and len(new) == 1 \
                        and (before.isspace() or before in "\"'") \
                        and re.match(r"(?:[.?…,;—]*[\"']?(?:\s|$)|!+[\"']?\s*$)", text[match.end():]):
                    replies.append(len(out))
            elif number is not None:
                new = [Word(part, raw=number) for part in number_words(number).split()]
            elif other in PUNCTUATION:
                if not (other == "'" and before.isalnum() and match.end() < len(text) and text[match.end()].isalnum()):
                    out.append(Punct(other))
                if other in ".!?;…":
                    fresh = True
                attach = False
                continue
            if new and attach:
                new[0] = new[0]._replace(attach=True)
            out.extend(new)
            attach = False
            fresh = fresh and not new
        # "Ss!" and "Sh, ss, tsk" are a hiss. Beside an ordinary word the two letters
        # stay letters, as in "the ss", "mm:ss" and a variable named ss. Quotation
        # marks and brackets do not part them from that word: "written as 'ss'".
        for place in short:
            first, last = place, place + 1
            while first and (isinstance(out[first - 1], Word) or out[first - 1].mark in "\"'()"):
                first -= 1
            while last < len(out) and (isinstance(out[last], Word) or out[last].mark in "\"'()"):
                last += 1
            if all(token.text in _SOUNDS or (token.phones is not None and len(set(token.text)) == 1)
                   for token in out[first:last] if isinstance(token, Word)):
                out[place] = out[place]._replace(phones=((out[place].text[0], 0),))
        # "k" is "okay" as a reply by itself; beside a word or a figure it is the letter.
        for place in reversed(replies):
            if self._reply(out, place):
                raw = out[place].raw
                out[place:place + 1] = self._chat_words(self.chat[raw.lower()], raw)
        return out


_DEFAULT = None


def tokens(text, is_word=None):
    """Words and punctuation marks of ``text``. ``is_word(spelling)`` tells
    whether the dictionary knows a spelling (used for capitals and chat forms)."""
    global _DEFAULT
    if is_word is None:
        if _DEFAULT is None:
            _DEFAULT = Normalizer()
        return _DEFAULT.tokens(text)
    return Normalizer(is_word).tokens(text)
