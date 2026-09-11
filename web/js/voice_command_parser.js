/**
 * Voice Command Parser for Web Pharmacy Billing.
 * Parses natural spoken voice commands into structured data:
 * { quantity: number, unit: 'strip' | 'loose', itemNameGuess: string, rawText: string }
 * Supports English & Hindi/Hinglish numbers (1-20), preserves dosage strengths like "dolo 650".
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.VoiceCommandParser = factory();
    root.parseVoiceCommand = root.VoiceCommandParser.parseVoiceCommand;
  }
}(typeof self !== 'undefined' ? self : this, function () {

  const NUMBER_WORDS = {
    // English (1-20)
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,

    // Hindi / Hinglish (1-20)
    'ek': 1, 'aek': 1, 'ik': 1,
    'do': 2, 'doo': 2,
    'teen': 3, 'tin': 3,
    'char': 4, 'chaar': 4,
    'paanch': 5, 'panch': 5,
    'che': 6, 'chhe': 6, 'chheh': 6, 'chha': 6,
    'saat': 7, 'sat': 7,
    'aath': 8, 'ath': 8,
    'nau': 9, 'no': 9,
    'das': 10, 'dus': 10,
    'gyarah': 11, 'gyara': 11,
    'barah': 12, 'bara': 12,
    'terah': 13, 'tera': 13,
    'chaudah': 14, 'chauda': 14,
    'pandrah': 15, 'pandra': 15,
    'solah': 16, 'sola': 16,
    'satrah': 17, 'satra': 17,
    'atharah': 18, 'athara': 18, 'attharah': 18,
    'unnees': 19, 'unnis': 19,
    'bees': 20, 'bis': 20
  };

  const STRIP_KEYWORDS = new Set([
    'strip', 'strips', 'patti', 'pattiyan', 'pattiya', 'patte', 'patta',
    'pack', 'packs', 'packet', 'packets', 'box', 'boxes'
  ]);

  const LOOSE_KEYWORDS = new Set([
    'loose', 'khula', 'khuli', 'khule',
    'tablet', 'tablets', 'tab', 'tabs',
    'pill', 'pills', 'goli', 'goliyan', 'goliya',
    'piece', 'pieces', 'single'
  ]);

  const FILLER_WORDS = new Set([
    'of', 'ka', 'ki', 'ke', 'ko', 'se', 'me', 'mein',
    'wali', 'wale', 'wala',
    'chahiye', 'de', 'dena', 'dijiye', 'dijie',
    'aur', 'and', 'please', 'bhai', 'bhaiya', 'sir', 'ji',
    'dawa', 'dawai', 'medicine', 'dawain',
    'give', 'need', 'want', 'add', 'put', 'le', 'lo'
  ]);

  function parseVoiceCommand(spokenText) {
    const raw = (spokenText || '').trim();
    if (!raw) {
      return {
        quantity: 1,
        unit: 'strip',
        itemNameGuess: '',
        rawText: ''
      };
    }

    const tokens = raw.split(/\s+/);
    const lowerTokens = tokens.map(t => t.toLowerCase().replace(/[^\w\d]/g, ''));

    const consumedIndices = new Set();
    let parsedQty = null;
    let parsedUnit = null;

    // 1. Identify unit tokens and locations
    const unitIndices = [];
    for (let i = 0; i < lowerTokens.length; i++) {
      const word = lowerTokens[i];
      if (LOOSE_KEYWORDS.has(word)) {
        parsedUnit = parsedUnit || 'loose';
        consumedIndices.add(i);
        unitIndices.push(i);
      } else if (STRIP_KEYWORDS.has(word)) {
        parsedUnit = parsedUnit || 'strip';
        consumedIndices.add(i);
        unitIndices.push(i);
      }
    }

    function getNumberFromToken(idx, isBeforeUnit = false) {
      if (idx < 0 || idx >= lowerTokens.length) return null;
      const word = lowerTokens[idx];

      if (NUMBER_WORDS[word] !== undefined) {
        return NUMBER_WORDS[word];
      }

      const digitVal = parseInt(word, 10);
      if (!isNaN(digitVal) && String(digitVal) === word) {
        if (isBeforeUnit) {
          return digitVal;
        }
        // Without unit: values >= 100 are likely dosages (e.g. 500, 650)
        if (digitVal > 0 && digitVal <= 50) {
          return digitVal;
        }
      }
      return null;
    }

    // 2. Quantity extraction:
    // Priority A: Number directly before (or within 1 filler of) a unit keyword
    for (const uIdx of unitIndices) {
      let prevIdx = uIdx - 1;
      while (prevIdx >= 0 && (consumedIndices.has(prevIdx) || FILLER_WORDS.has(lowerTokens[prevIdx]))) {
        prevIdx--;
      }
      if (prevIdx >= 0 && !consumedIndices.has(prevIdx)) {
        const num = getNumberFromToken(prevIdx, true);
        if (num !== null) {
          parsedQty = num;
          consumedIndices.add(prevIdx);
          break;
        }
      }
    }

    // Priority B: Check index 0 or 1 at start of utterance
    if (parsedQty === null) {
      for (let i = 0; i < lowerTokens.length && i < 2; i++) {
        if (!consumedIndices.has(i)) {
          const num = getNumberFromToken(i, false);
          if (num !== null) {
            parsedQty = num;
            consumedIndices.add(i);
            break;
          }
        }
      }
    }

    const finalQty = parsedQty !== null ? parsedQty : 1;
    const finalUnit = parsedUnit || 'strip';

    // 3. Extract Item Name Guess
    const nameTokens = [];
    for (let i = 0; i < tokens.length; i++) {
      if (consumedIndices.has(i)) continue;
      const low = lowerTokens[i];
      if (FILLER_WORDS.has(low)) continue;
      // "do" at the very end of utterance is verb 'give'
      if (low === 'do' && i === tokens.length - 1) continue;

      nameTokens.push(tokens[i]);
    }

    const itemNameGuess = nameTokens.join(' ').trim();

    return {
      quantity: finalQty,
      unit: finalUnit,
      itemNameGuess: itemNameGuess.length > 0 ? itemNameGuess : raw,
      rawText: raw
    };
  }

  return {
    parseVoiceCommand: parseVoiceCommand
  };
}));
