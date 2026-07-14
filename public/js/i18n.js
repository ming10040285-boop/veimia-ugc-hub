/**
 * i18n - Internationalization module for VEIMIA UGC Hub
 *
 * Loads language JSON files based on campaign market config.
 * Falls back to Korean (ko) when a key is missing in the target language.
 *
 * Usage:
 *   await I18n.init('ja');
 *   const label = t('submit_button');
 */
(function (global) {
  'use strict';

  /** @type {Object<string, string>} Current language translations */
  var _translations = {};

  /** @type {Object<string, string>} Korean fallback translations */
  var _fallback = {};

  /** @type {string} Currently loaded market */
  var _currentMarket = 'ko';

  /** @type {boolean} Whether the module has been initialized */
  var _initialized = false;

  /**
   * Fetches a language JSON file from /i18n/{market}.json
   * @param {string} market - The market code (e.g., 'ko', 'ja', 'en')
   * @returns {Promise<Object>} The parsed translations object
   */
  function _loadLanguageFile(market) {
    return fetch('/i18n/' + market + '.json')
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Failed to load language file: /i18n/' + market + '.json (HTTP ' + response.status + ')');
        }
        return response.json();
      });
  }

  /**
   * Initializes the i18n module by loading the appropriate language file.
   * Always loads Korean as fallback. If the target market is not Korean,
   * also loads the target language file.
   *
   * @param {string} [market='ko'] - The market code to load ('ko', 'ja', or 'en')
   * @returns {Promise<void>}
   */
  function initI18n(market) {
    market = market || 'ko';
    _currentMarket = market;

    // Always load Korean as the fallback language
    return _loadLanguageFile('ko')
      .then(function (koData) {
        _fallback = koData;

        if (market === 'ko') {
          // Korean is both the target and the fallback
          _translations = koData;
          _initialized = true;
          return;
        }

        // Load the target language file
        return _loadLanguageFile(market)
          .then(function (targetData) {
            _translations = targetData;
            _initialized = true;
          })
          .catch(function (error) {
            // If target language file fails to load, fall back entirely to Korean
            console.warn('[i18n] Could not load language file for "' + market + '", falling back to Korean.', error);
            _translations = koData;
            _initialized = true;
          });
      });
  }

  /**
   * Retrieves a localized string for the given key.
   * If the key is missing in the target language, returns the Korean default
   * and logs the missing key identifier via console.warn.
   *
   * @param {string} key - The translation key identifier
   * @returns {string} The localized string, or the key itself if not found in any language
   */
  function t(key) {
    // Check target language translations first
    if (_translations.hasOwnProperty(key) && _translations[key] !== undefined && _translations[key] !== null) {
      return _translations[key];
    }

    // Fall back to Korean
    if (_fallback.hasOwnProperty(key) && _fallback[key] !== undefined && _fallback[key] !== null) {
      console.warn('[i18n] Missing translation for key "' + key + '" in market "' + _currentMarket + '", using Korean fallback.');
      return _fallback[key];
    }

    // Key not found in any language file
    console.warn('[i18n] Translation key "' + key + '" not found in any language file.');
    return key;
  }

  /**
   * Returns the currently loaded market code.
   * @returns {string}
   */
  function getCurrentMarket() {
    return _currentMarket;
  }

  /**
   * Returns whether the module has been initialized.
   * @returns {boolean}
   */
  function isInitialized() {
    return _initialized;
  }

  // Export to global scope for use via <script> tag
  global.I18n = {
    init: initI18n,
    t: t,
    getCurrentMarket: getCurrentMarket,
    isInitialized: isInitialized
  };

  // Also expose t() at the top level for convenience
  global.t = t;

})(typeof window !== 'undefined' ? window : this);
