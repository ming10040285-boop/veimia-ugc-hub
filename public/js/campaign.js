/**
 * campaign.js - Main campaign page controller for VEIMIA UGC Hub
 *
 * Responsibilities:
 * - Extract campaign_id from URL query parameter
 * - Fetch campaign config JSON
 * - Initialize i18n with the campaign's market
 * - Render page sections based on config
 * - Expose skeleton functions for later tasks
 */
(function (global) {
  'use strict';

  /** @type {Object|null} The loaded campaign configuration */
  var _campaignConfig = null;

  /**
   * Returns the currently loaded campaign configuration.
   * @returns {Object|null}
   */
  function getCampaignConfig() {
    return _campaignConfig;
  }

  /**
   * Extracts the campaign_id from URL query parameters.
   * @returns {string|null} The campaign ID or null if not found
   */
  function getCampaignIdFromUrl() {
    var params = new URLSearchParams(window.location.search);
    return params.get('campaign') || null;
  }

  /**
   * Fetches the campaign configuration JSON from the server.
   * @param {string} campaignId - The campaign identifier
   * @returns {Promise<Object>} The parsed campaign configuration
   */
  function fetchCampaignConfig(campaignId) {
    // Try read_campaign API first (reads directly from GitHub, no cache)
    var apiUrl = '/api/admin/read_campaign?id=' + encodeURIComponent(campaignId);
    return fetch(apiUrl).then(function (response) {
      if (response.ok) {
        return response.json();
      }
      // Fallback to static file if API fails
      var staticUrl = '/config/campaigns/' + encodeURIComponent(campaignId) + '.json';
      return fetch(staticUrl).then(function (resp) {
        if (!resp.ok) {
          throw new Error('Failed to load campaign config (HTTP ' + resp.status + ')');
        }
        return resp.json();
      });
    });
  }

  /**
   * Renders the hero section with the campaign's hero image.
   * @param {Object} config - The campaign configuration
   */
  function renderHero(config) {
    var heroImage = document.getElementById('hero-image');
    if (heroImage && config.hero_image_url) {
      heroImage.src = config.hero_image_url;
      heroImage.alt = t('campaign_hero_alt');
    }
    // Set hero title from campaign name
    var heroTitle = document.getElementById('hero-title');
    if (heroTitle && config.campaign_name) {
      heroTitle.textContent = config.campaign_name;
    }
  }

  /**
   * Renders the introduction section with campaign text.
   * @param {Object} config - The campaign configuration
   */
  function renderIntroduction(config) {
    var introText = document.getElementById('introduction-text');
    if (introText && config.introduction_text) {
      introText.textContent = config.introduction_text;
    }
  }

  /**
   * Truncates text to a maximum length, adding ellipsis if exceeded.
   * @param {string} text - The text to truncate
   * @param {number} maxLength - Maximum visible characters
   * @returns {string} Truncated text with ellipsis or original text
   */
  function truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  }

  /**
   * Validates a URL for display (http/https scheme, max 2048 chars).
   * @param {string|null} url - The URL to validate
   * @returns {boolean} Whether the URL is valid for display
   */
  function isValidDisplayUrl(url) {
    if (!url) return false;
    if (url.length > 2048 && !url.startsWith('data:')) return false;
    // Allow Base64 data URLs (from local upload)
    if (url.startsWith('data:image/')) return true;
    try {
      var parsed = new URL(url);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch (e) {
      return false;
    }
  }

  /**
   * Renders a single product display (for product_mode "single").
   * @param {Object} product - The campaign product object
   */
  function renderSingleProduct(product) {
    var container = document.getElementById('product-container');
    if (!container || !product) return;

    container.setAttribute('data-product-mode', 'single');
    container.setAttribute('data-product-id', product.product_id);

    // Truncate description at 200 characters
    var description = truncateText(product.short_description, 200);

    // Determine button visibility
    var showDetailBtn = isValidDisplayUrl(product.product_detail_url);
    var showSizeGuideBtn = isValidDisplayUrl(product.size_guide_url);

    // Build size options
    var sizeOptions = '<option value="">' + t('size_label') + '</option>';
    if (product.available_sizes && product.available_sizes.length > 0) {
      for (var i = 0; i < product.available_sizes.length; i++) {
        sizeOptions += '<option value="' + product.available_sizes[i] + '">' + product.available_sizes[i] + '</option>';
      }
    }

    // Build color options
    var colorOptions = '<option value="">' + t('color_label') + '</option>';
    if (product.available_colors && product.available_colors.length > 0) {
      for (var j = 0; j < product.available_colors.length; j++) {
        colorOptions += '<option value="' + product.available_colors[j] + '">' + product.available_colors[j] + '</option>';
      }
    }

    // Build HTML
    var html = '';
    html += '<div class="single-product">';

    // Product image
    html += '<div class="single-product__image-wrapper">';
    html += '<img class="single-product__image" src="' + product.product_image_url + '" alt="' + t('product_image_alt') + '">';
    html += '</div>';

    // Product name and ID
    html += '<div class="single-product__info">';
    html += '<h2 class="single-product__name">' + product.product_name + '</h2>';
    html += '<span class="single-product__id" style="display:none;">' + product.product_id + '</span>';
    html += '</div>';

    // Short description
    html += '<p class="single-product__description">' + description + '</p>';

    // Action buttons
    html += '<div class="single-product__actions">';
    if (showDetailBtn) {
      html += '<a href="' + product.product_detail_url + '" target="_blank" rel="noopener noreferrer" class="btn btn--secondary single-product__detail-btn">' + t('product_detail_button') + '</a>';
    }
    if (showSizeGuideBtn) {
      html += '<button type="button" class="btn btn--secondary single-product__size-guide-btn" onclick="Campaign.showSizeGuidePopup(\'' + product.size_guide_url.replace(/'/g, "\\'") + '\')">' + t('size_guide_button') + '</button>';
    }
    html += '</div>';

    // Size and color prompt
    html += '<p class="single-product__prompt">' + t('size_color_prompt') + '</p>';

    // Size selection
    html += '<div class="single-product__select-group">';
    html += '<label for="size-select">' + t('size_label') + '</label>';
    html += '<select id="size-select" class="single-product__select" name="selected_size">';
    html += sizeOptions;
    html += '</select>';
    html += '</div>';

    // Color selection
    html += '<div class="single-product__select-group">';
    html += '<label for="color-select">' + t('color_label') + '</label>';
    html += '<select id="color-select" class="single-product__select" name="selected_color">';
    html += colorOptions;
    html += '</select>';
    html += '</div>';

    html += '</div>';

    container.innerHTML = html;
  }

  /** @type {string|null} Currently selected product_id in multiple-product mode */
  var _selectedProductId = null;

  /**
   * Returns the currently selected product ID (multiple-product mode).
   * @returns {string|null}
   */
  function getSelectedProductId() {
    return _selectedProductId;
  }

  /**
   * Renders size and color dropdowns for the selected product in multiple-product mode.
   * Clears previous selections when a new product is selected.
   * @param {Object} product - The selected product object
   */
  function renderProductOptions(product) {
    var optionsContainer = document.getElementById('multi-product-options');
    if (!optionsContainer) return;

    // Build size options
    var sizeOptions = '<option value="">' + t('size_label') + '</option>';
    if (product.available_sizes && product.available_sizes.length > 0) {
      for (var i = 0; i < product.available_sizes.length; i++) {
        sizeOptions += '<option value="' + product.available_sizes[i] + '">' + product.available_sizes[i] + '</option>';
      }
    }

    // Build color options
    var colorOptions = '<option value="">' + t('color_label') + '</option>';
    if (product.available_colors && product.available_colors.length > 0) {
      for (var j = 0; j < product.available_colors.length; j++) {
        colorOptions += '<option value="' + product.available_colors[j] + '">' + product.available_colors[j] + '</option>';
      }
    }

    var html = '';
    html += '<p class="multi-product-options__prompt">' + t('size_color_prompt') + '</p>';

    // Size selection
    html += '<div class="multi-product-options__select-group">';
    html += '<label for="size-select">' + t('size_label') + '</label>';
    html += '<select id="size-select" class="multi-product-options__select" name="selected_size">';
    html += sizeOptions;
    html += '</select>';
    html += '</div>';

    // Color selection
    html += '<div class="multi-product-options__select-group">';
    html += '<label for="color-select">' + t('color_label') + '</label>';
    html += '<select id="color-select" class="multi-product-options__select" name="selected_color">';
    html += colorOptions;
    html += '</select>';
    html += '</div>';

    optionsContainer.innerHTML = html;
    optionsContainer.style.display = '';
  }

  /**
   * Handles product card selection in multiple-product mode.
   * @param {string} productId - The ID of the selected product
   * @param {Array} products - Full array of products for lookup
   */
  function selectProduct(productId, products) {
    // Update selected state
    _selectedProductId = productId;

    // Update active class on cards
    var cards = document.querySelectorAll('.product-card');
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].getAttribute('data-product-id') === productId) {
        cards[i].classList.add('product-card--active');
      } else {
        cards[i].classList.remove('product-card--active');
      }
    }

    // Find the selected product
    var selectedProduct = null;
    for (var j = 0; j < products.length; j++) {
      if (products[j].product_id === productId) {
        selectedProduct = products[j];
        break;
      }
    }

    // Render size/color options for selected product (clears previous selections)
    if (selectedProduct) {
      renderProductOptions(selectedProduct);
    }

    // Clear product selection prompt error if visible
    var promptEl = document.getElementById('product-selection-prompt');
    if (promptEl) {
      promptEl.style.display = 'none';
    }
  }

  /**
   * Shows a product detail modal overlay with full product information.
   * Displays: full description, all product images, available sizes, and available colors.
   * @param {Object} product - The product object to display details for
   */
  function showProductDetail(product) {
    if (!product) return;

    // Remove existing modal if present
    var existingModal = document.getElementById('product-detail-modal');
    if (existingModal) {
      existingModal.parentNode.removeChild(existingModal);
    }

    // Build modal HTML
    var html = '';
    html += '<div class="product-detail-modal" id="product-detail-modal" role="dialog" aria-modal="true" aria-label="' + product.product_name + '">';
    html += '<div class="product-detail-modal__overlay" data-action="close"></div>';
    html += '<div class="product-detail-modal__content">';

    // Close button
    html += '<button type="button" class="product-detail-modal__close" data-action="close" aria-label="' + t('product_detail_modal_close') + '">&times;</button>';

    // Product image
    html += '<div class="product-detail-modal__image-wrapper">';
    html += '<img class="product-detail-modal__image" src="' + product.product_image_url + '" alt="' + product.product_name + ' - ' + t('product_image_alt') + '">';
    html += '</div>';

    // Product info
    html += '<div class="product-detail-modal__info">';
    html += '<h2 class="product-detail-modal__name">' + product.product_name + '</h2>';
    html += '<span class="product-detail-modal__id" style="display:none;">' + product.product_id + '</span>';

    // Full description (not truncated)
    if (product.short_description) {
      html += '<p class="product-detail-modal__description">' + product.short_description + '</p>';
    }

    // Available sizes
    html += '<div class="product-detail-modal__section">';
    html += '<h3 class="product-detail-modal__section-title">' + t('product_detail_sizes_label') + '</h3>';
    if (product.available_sizes && product.available_sizes.length > 0) {
      html += '<ul class="product-detail-modal__tag-list">';
      for (var i = 0; i < product.available_sizes.length; i++) {
        html += '<li class="product-detail-modal__tag">' + product.available_sizes[i] + '</li>';
      }
      html += '</ul>';
    } else {
      html += '<p class="product-detail-modal__empty-info">' + t('product_detail_no_sizes') + '</p>';
    }
    html += '</div>';

    // Available colors
    html += '<div class="product-detail-modal__section">';
    html += '<h3 class="product-detail-modal__section-title">' + t('product_detail_colors_label') + '</h3>';
    if (product.available_colors && product.available_colors.length > 0) {
      html += '<ul class="product-detail-modal__tag-list">';
      for (var j = 0; j < product.available_colors.length; j++) {
        html += '<li class="product-detail-modal__tag">' + product.available_colors[j] + '</li>';
      }
      html += '</ul>';
    } else {
      html += '<p class="product-detail-modal__empty-info">' + t('product_detail_no_colors') + '</p>';
    }
    html += '</div>';

    // External link (if product_detail_url is configured)
    if (isValidDisplayUrl(product.product_detail_url)) {
      html += '<div class="product-detail-modal__external">';
      html += '<a href="' + product.product_detail_url + '" target="_blank" rel="noopener noreferrer" class="btn btn--secondary product-detail-modal__external-link">' + t('product_detail_external_link') + '</a>';
      html += '</div>';
    }

    html += '</div>'; // .product-detail-modal__info
    html += '</div>'; // .product-detail-modal__content
    html += '</div>'; // .product-detail-modal

    // Append to body
    var modalEl = document.createElement('div');
    modalEl.innerHTML = html;
    var modal = modalEl.firstChild;
    document.body.appendChild(modal);

    // Prevent body scroll while modal is open
    document.body.style.overflow = 'hidden';

    // Close handlers
    function closeModal() {
      var modalNode = document.getElementById('product-detail-modal');
      if (modalNode) {
        modalNode.parentNode.removeChild(modalNode);
      }
      document.body.style.overflow = '';
    }

    // Click to close (overlay and close button)
    modal.addEventListener('click', function (e) {
      if (e.target.getAttribute('data-action') === 'close') {
        closeModal();
      }
    });

    // Escape key to close
    function handleEscape(e) {
      if (e.key === 'Escape' || e.keyCode === 27) {
        closeModal();
        document.removeEventListener('keydown', handleEscape);
      }
    }
    document.addEventListener('keydown', handleEscape);
  }

  /**
   * Renders multiple products display (for product_mode "multiple").
   * Shows a product card grid with only active (status: "open") products.
   * @param {Array} products - Array of campaign product objects
   */
  function renderMultipleProducts(products) {
    var container = document.getElementById('product-container');
    if (!container) return;

    container.setAttribute('data-product-mode', 'multiple');
    container.setAttribute('data-product-count', products ? products.length : 0);

    // Filter to only active (open) products
    var activeProducts = [];
    if (products && products.length > 0) {
      for (var i = 0; i < products.length; i++) {
        if (products[i].status === 'open') {
          activeProducts.push(products[i]);
        }
      }
    }

    // Show "no products available" message if no active products
    if (activeProducts.length === 0) {
      container.innerHTML = '<div class="multi-product__empty">' +
        '<p class="multi-product__empty-message">' + t('no_products_available') + '</p>' +
        '</div>';
      return;
    }

    var html = '';
    html += '<div class="multi-product">';

    // Product card grid
    html += '<div class="product-card-grid" role="list" aria-label="' + t('select_product_prompt') + '">';

    for (var k = 0; k < activeProducts.length; k++) {
      var product = activeProducts[k];
      var description = truncateText(product.short_description, 120);

      html += '<div class="product-card" role="listitem" data-product-id="' + product.product_id + '">';

      // Product image
      html += '<div class="product-card__image-wrapper">';
      html += '<img class="product-card__image" src="' + product.product_image_url + '" alt="' + product.product_name + ' - ' + t('product_image_alt') + '">';
      html += '</div>';

      // Product info
      html += '<div class="product-card__body">';
      html += '<h3 class="product-card__name">' + product.product_name + '</h3>';
      html += '<span class="product-card__id" style="display:none;">' + product.product_id + '</span>';
      html += '<p class="product-card__description">' + description + '</p>';

      // Action buttons
      html += '<div class="product-card__actions">';
      html += '<button type="button" class="btn btn--secondary product-card__detail-btn" data-detail-product-id="' + product.product_id + '">' + t('product_detail_button') + '</button>';
      html += '<button type="button" class="btn btn--primary product-card__select-btn" data-product-id="' + product.product_id + '">';
      html += '선택';
      html += '</button>';
      html += '</div>';

      html += '</div>'; // .product-card__body
      html += '</div>'; // .product-card
    }

    html += '</div>'; // .product-card-grid

    // Product selection prompt (hidden by default, shown on validation)
    html += '<p id="product-selection-prompt" class="multi-product__selection-prompt" style="display:none;">' + t('select_product_prompt') + '</p>';

    // Options area (size/color dropdowns, shown after product selection)
    html += '<div id="multi-product-options" class="multi-product-options" style="display:none;"></div>';

    html += '</div>'; // .multi-product

    container.innerHTML = html;

    // Bind select button click events
    var selectButtons = container.querySelectorAll('.product-card__select-btn');
    for (var m = 0; m < selectButtons.length; m++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          var productId = btn.getAttribute('data-product-id');
          selectProduct(productId, activeProducts);
        });
      })(selectButtons[m]);
    }

    // Bind detail button click events (opens product detail modal)
    var detailButtons = container.querySelectorAll('.product-card__detail-btn');
    for (var n = 0; n < detailButtons.length; n++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          var productId = btn.getAttribute('data-detail-product-id');
          for (var p = 0; p < activeProducts.length; p++) {
            if (activeProducts[p].product_id === productId) {
              showProductDetail(activeProducts[p]);
              break;
            }
          }
        });
      })(detailButtons[n]);
    }
  }

  /**
   * Renders the registration form with client-side validation.
   * @param {Object} config - The campaign configuration
   */
  function renderForm(config) {
    var container = document.getElementById('form-container');
    if (!container) return;

    container.setAttribute('data-campaign-id', config.campaign_id);

    // Build form HTML
    var html = '';
    html += '<form id="registration-form" class="registration-form" novalidate>';

    // Member type radio buttons (above Instagram ID field)
    html += '<fieldset class="form-field form-field--radio" data-field="member_type" id="member-type-fieldset">';
    html += '<legend>' + t('member_type_label') + '</legend>';
    html += '<label class="form-field__radio-label">';
    html += '<input type="radio" name="member_type" value="new">';
    html += '<span>' + t('member_type_new') + '</span>';
    html += '</label>';
    html += '<label class="form-field__radio-label">';
    html += '<input type="radio" name="member_type" value="returning">';
    html += '<span>' + t('member_type_returning') + '</span>';
    html += '</label>';
    html += '<span class="form-field__error"></span>';
    html += '</fieldset>';

    // Instagram ID field
    html += '<div class="form-field" data-field="instagram_id">';
    html += '<label for="field-instagram-id">' + t('instagram_id_label') + '</label>';
    html += '<input type="text" id="field-instagram-id" name="instagram_id" maxlength="200" autocomplete="off">';
    html += '<span class="form-field__error"></span>';
    html += '</div>';

    // Name field
    html += '<div class="form-field" data-field="name">';
    html += '<label for="field-name">' + t('name_label') + '</label>';
    html += '<input type="text" id="field-name" name="name" maxlength="100" autocomplete="name">';
    html += '<span class="form-field__error"></span>';
    html += '</div>';

    // Phone field
    html += '<div class="form-field" data-field="phone">';
    html += '<label for="field-phone">' + t('phone_label') + '</label>';
    html += '<input type="tel" id="field-phone" name="phone" maxlength="20" autocomplete="tel">';
    html += '<span class="form-field__error"></span>';
    html += '</div>';

    // Address field
    html += '<div class="form-field" data-field="address">';
    html += '<label for="field-address">' + t('address_label') + '</label>';
    html += '<input type="text" id="field-address" name="address" maxlength="300" autocomplete="street-address">';
    html += '<span class="form-field__error"></span>';
    html += '</div>';

    // Postal code field
    html += '<div class="form-field" data-field="postal_code">';
    html += '<label for="field-postal-code">' + t('postal_code_label') + '</label>';
    html += '<input type="text" id="field-postal-code" name="postal_code" maxlength="10" autocomplete="postal-code">';
    html += '<span class="form-field__error"></span>';
    html += '</div>';

    // Submit button
    html += '<button type="submit" class="btn btn--primary registration-form__submit">' + t('submit_button') + '</button>';

    // Consent notice (simple text below submit button)
    html += '<p class="consent-notice" style="text-align:center;font-size:0.8rem;color:#888;margin-top:12px;">参与活动即同意品牌方用来宣传与品牌推广使用。</p>';

    // Hidden consent field (always true since user submits = agrees)
    html += '<input type="hidden" id="field-consent" name="consent" value="true">';

    // Message area for success/error feedback
    html += '<div id="form-message" class="form-message" style="display:none;"></div>';

    html += '</form>';

    container.innerHTML = html;

    // Bind form submission
    var form = document.getElementById('registration-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        handleFormSubmit(config);
      });
    }
  }

  /**
   * Validates the registration form fields.
   * @param {Object} config - The campaign configuration
   * @returns {Object|null} The validated form data object, or null if validation fails
   */
  function validateForm(config) {
    var isValid = true;

    // Clear all previous errors
    var errorFields = document.querySelectorAll('.form-field.field-error, .consent-section.field-error');
    for (var i = 0; i < errorFields.length; i++) {
      errorFields[i].classList.remove('field-error');
      var errSpan = errorFields[i].querySelector('.form-field__error');
      if (errSpan) errSpan.textContent = '';
    }

    // Also clear size/color select errors
    var sizeSelect = document.getElementById('size-select');
    var colorSelect = document.getElementById('color-select');
    if (sizeSelect) sizeSelect.classList.remove('field-error');
    if (colorSelect) colorSelect.classList.remove('field-error');

    // Also clear member_type fieldset error
    var memberTypeFieldset = document.getElementById('member-type-fieldset');
    if (memberTypeFieldset) {
      memberTypeFieldset.classList.remove('field-error');
      var memberTypeErr = memberTypeFieldset.querySelector('.form-field__error');
      if (memberTypeErr) memberTypeErr.textContent = '';
    }

    // Helper to mark a field as invalid
    function markInvalid(fieldName, errorMessage) {
      var fieldEl = document.querySelector('.form-field[data-field="' + fieldName + '"]')
        || document.querySelector('.consent-section[data-field="' + fieldName + '"]');
      if (fieldEl) {
        fieldEl.classList.add('field-error');
        var errEl = fieldEl.querySelector('.form-field__error');
        if (errEl) errEl.textContent = errorMessage || t('validation_error');
      }
      isValid = false;
    }

    // Validate member_type radio buttons
    var memberTypeRadios = document.querySelectorAll('input[name="member_type"]');
    var selectedMemberType = '';
    for (var r = 0; r < memberTypeRadios.length; r++) {
      if (memberTypeRadios[r].checked) {
        selectedMemberType = memberTypeRadios[r].value;
        break;
      }
    }
    if (!selectedMemberType) {
      markInvalid('member_type', t('member_type_required_error'));
    }

    // Validate text fields
    var instagramId = (document.getElementById('field-instagram-id').value || '').trim();
    var name = (document.getElementById('field-name').value || '').trim();
    var phone = (document.getElementById('field-phone').value || '').trim();
    var address = (document.getElementById('field-address').value || '').trim();
    var postalCode = (document.getElementById('field-postal-code').value || '').trim();
    var consent = true; // Consent is implicit by submitting the form

    if (!instagramId || instagramId.length > 200) markInvalid('instagram_id');
    if (!name || name.length > 100) markInvalid('name');
    if (!phone || phone.length > 20) markInvalid('phone');
    if (!address || address.length > 300) markInvalid('address');
    if (!postalCode || postalCode.length > 10) markInvalid('postal_code');

    // Validate size and color from existing dropdowns
    var selectedSize = sizeSelect ? sizeSelect.value : '';
    var selectedColor = colorSelect ? colorSelect.value : '';

    if (!selectedSize) {
      if (sizeSelect) sizeSelect.classList.add('field-error');
      isValid = false;
    }
    if (!selectedColor) {
      if (colorSelect) colorSelect.classList.add('field-error');
      isValid = false;
    }

    // For multiple-product mode, check product selection
    var productId = null;
    if (config.product_mode === 'single') {
      productId = config.products[0].product_id;
    } else {
      productId = getSelectedProductId();
      if (!productId) {
        var promptEl = document.getElementById('product-selection-prompt');
        if (promptEl) promptEl.style.display = '';
        isValid = false;
      }
    }

    if (!isValid) return null;

    return {
      campaign_id: config.campaign_id,
      product_id: productId,
      member_type: selectedMemberType,
      selected_size: selectedSize,
      selected_color: selectedColor,
      instagram_id: instagramId,
      name: name,
      phone: phone,
      address: address,
      postal_code: postalCode,
      consent: true
    };
  }

  /**
   * Handles form submission: validates, POSTs to /api/register, shows feedback.
   * @param {Object} config - The campaign configuration
   */
  function handleFormSubmit(config) {
    var formData = validateForm(config);
    if (!formData) return;

    var submitBtn = document.querySelector('.registration-form__submit');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = t('loading') || '...';
    }

    fetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { status: response.status, body: data };
        });
      })
      .then(function (result) {
        var messageEl = document.getElementById('form-message');
        if (!messageEl) return;

        if (result.status === 200) {
          // Success
          messageEl.className = 'form-message form-message--success';
          messageEl.textContent = t('registration_success');
          messageEl.style.display = '';
          // Optionally hide the form fields
          var form = document.getElementById('registration-form');
          if (form) {
            var fields = form.querySelectorAll('.form-field, .registration-form__submit');
            for (var i = 0; i < fields.length; i++) {
              fields[i].style.display = 'none';
            }
          }
        } else {
          // Error response
          var errorMsg = '';
          var code = result.body && result.body.code;
          if (code === 'DUPLICATE_REGISTRATION') {
            errorMsg = t('duplicate_error');
          } else if (code === 'PRODUCT_UNAVAILABLE') {
            errorMsg = t('product_unavailable');
          } else if (code === 'INVALID_SIZE_COLOR') {
            errorMsg = t('invalid_size_color');
          } else if (code === 'SHEETS_UNAVAILABLE') {
            errorMsg = t('sheets_unavailable');
          } else if (code === 'TIMEOUT') {
            errorMsg = t('timeout_error');
          } else {
            errorMsg = (result.body && result.body.message) || t('error_generic');
          }

          messageEl.className = 'form-message form-message--error';
          messageEl.textContent = errorMsg;
          messageEl.style.display = '';
        }
      })
      .catch(function () {
        var messageEl = document.getElementById('form-message');
        if (messageEl) {
          messageEl.className = 'form-message form-message--error';
          messageEl.textContent = t('error_generic');
          messageEl.style.display = '';
        }
      })
      .finally(function () {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = t('submit_button');
        }
      });
  }

  /**
   * UGCCarousel - Auto-scrolling infinite loop carousel for UGC gallery images.
   * Uses requestAnimationFrame and CSS translateX transforms for smooth 60fps animation.
   * Default speed: 1 image width per 3 seconds.
   *
   * @param {HTMLElement} trackEl - The .ugc-carousel-track element
   * @param {number} imageCount - Number of original images (before cloning)
   * @constructor
   */
  function UGCCarousel(trackEl, imageCount) {
    this.track = trackEl;
    this.imageCount = imageCount;
    this.offset = 0;
    this.animationId = null;
    this.paused = false;
    this.lastTimestamp = null;
    this._resumeTimeout = null;
    this._touchStartX = null;

    // Determine image width based on viewport (matches CSS)
    this.imageWidth = window.innerWidth >= 768 ? 280 : 200;
    this.gap = 12; // matches CSS gap

    // Total width of the original set of images (used for seamless reset)
    this.totalOriginalWidth = imageCount * (this.imageWidth + this.gap);

    // Speed: 1 image width per 3 seconds = imageWidth / 3000 ms = pixels per millisecond
    this.speed = this.imageWidth / 3000;

    this._bindEvents();
  }

  /**
   * Starts the carousel animation loop using requestAnimationFrame.
   */
  UGCCarousel.prototype.start = function () {
    var self = this;
    self.lastTimestamp = null;

    function animate(timestamp) {
      if (self.paused) {
        self.lastTimestamp = null;
        self.animationId = requestAnimationFrame(animate);
        return;
      }

      if (!self.lastTimestamp) {
        self.lastTimestamp = timestamp;
      }

      var elapsed = timestamp - self.lastTimestamp;
      self.lastTimestamp = timestamp;

      // Advance offset by speed * elapsed time
      self.offset += self.speed * elapsed;

      // When offset passes the total width of original images, reset seamlessly
      if (self.offset >= self.totalOriginalWidth) {
        self.offset -= self.totalOriginalWidth;
      }

      self.track.style.transform = 'translateX(' + (-self.offset) + 'px)';
      self.animationId = requestAnimationFrame(animate);
    }

    self.animationId = requestAnimationFrame(animate);
  };

  /**
   * Stops the carousel animation.
   */
  UGCCarousel.prototype.stop = function () {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
  };

  /**
   * Pauses the carousel (keeps rAF running but doesn't advance offset).
   * Cancels any pending resume timeout.
   */
  UGCCarousel.prototype.pause = function () {
    this.paused = true;
    if (this._resumeTimeout) {
      clearTimeout(this._resumeTimeout);
      this._resumeTimeout = null;
    }
  };

  /**
   * Resumes the carousel from paused position.
   */
  UGCCarousel.prototype.resume = function () {
    this.paused = false;
    this.lastTimestamp = null;
  };

  /**
   * Schedules a resume after a 300ms delay.
   * Cancels any previously scheduled resume.
   */
  UGCCarousel.prototype._scheduleResume = function () {
    var self = this;
    if (self._resumeTimeout) {
      clearTimeout(self._resumeTimeout);
    }
    self._resumeTimeout = setTimeout(function () {
      self._resumeTimeout = null;
      self.resume();
    }, 300);
  };

  /**
   * Binds hover and touch events for pause/resume behavior.
   * Implements swipe detection on mobile: if swipe delta >= 30px, advances one image.
   * @private
   */
  UGCCarousel.prototype._bindEvents = function () {
    var self = this;
    var wrapper = self.track.parentElement;

    if (!wrapper) return;

    // Desktop: pause on hover, resume with 300ms delay on mouse leave
    wrapper.addEventListener('mouseenter', function () {
      self.pause();
    });
    wrapper.addEventListener('mouseleave', function () {
      self._scheduleResume();
    });

    // Mobile: pause on touch start, track touch position for swipe detection
    wrapper.addEventListener('touchstart', function (e) {
      self.pause();
      if (e.touches && e.touches.length > 0) {
        self._touchStartX = e.touches[0].clientX;
      }
    }, { passive: true });

    // Mobile: detect swipe on touch end, then resume with 300ms delay
    wrapper.addEventListener('touchend', function (e) {
      var endX = null;
      if (e.changedTouches && e.changedTouches.length > 0) {
        endX = e.changedTouches[0].clientX;
      }

      // Swipe detection: if start and end positions are captured
      if (self._touchStartX !== null && endX !== null) {
        var delta = endX - self._touchStartX;
        var step = self.imageWidth + self.gap;

        if (Math.abs(delta) >= 30) {
          if (delta < 0) {
            // Swipe left: advance forward
            self.offset += step;
          } else {
            // Swipe right: go back
            self.offset -= step;
          }

          // Keep offset within valid range
          if (self.offset < 0) {
            self.offset += self.totalOriginalWidth;
          } else if (self.offset >= self.totalOriginalWidth) {
            self.offset -= self.totalOriginalWidth;
          }

          // Apply transform immediately
          self.track.style.transform = 'translateX(' + (-self.offset) + 'px)';
        }
      }

      self._touchStartX = null;
      self._scheduleResume();
    }, { passive: true });
  };

  /**
   * Destroys the carousel, stopping animation and removing references.
   */
  UGCCarousel.prototype.destroy = function () {
    this.stop();
    this.track = null;
  };

  /** @type {UGCCarousel|null} Active carousel instance for cleanup */
  var _activeCarousel = null;

  /**
   * Checks if the user prefers reduced motion.
   * @returns {boolean}
   */
  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /**
   * Renders the UGC gallery section.
   * - 0 posts: hides section entirely
   * - 1 post: displays single image statically
   * - 2+ posts: displays auto-scrolling infinite carousel (or static row if prefers-reduced-motion)
   * @param {Array} ugcPosts - Array of UGC post objects
   */
  function renderUGCGallery(ugcPosts) {
    var section = document.getElementById('ugc-gallery-section');
    var container = document.getElementById('ugc-gallery-container');

    if (!section) {
      return;
    }

    // Destroy previous carousel if any
    if (_activeCarousel) {
      _activeCarousel.destroy();
      _activeCarousel = null;
    }

    // Hide entire section if no posts configured
    if (!ugcPosts || ugcPosts.length === 0) {
      section.style.display = 'none';
      return;
    }

    // Show section
    section.style.display = '';

    // Sort by display_order ascending and limit to 20
    var sortedPosts = ugcPosts
      .slice()
      .sort(function (a, b) {
        return (a.display_order || 0) - (b.display_order || 0);
      })
      .slice(0, 20);

    // Build gallery HTML
    var html = '';

    // Section title
    html += '<h2 class="ugc-gallery__title">' + t('ugc_gallery_title') + '</h2>';

    // Single post: display statically (no carousel)
    if (sortedPosts.length === 1) {
      var singlePost = sortedPosts[0];
      var singleAlt = t('ugc_gallery_title') + ' 1';
      html += '<div class="ugc-gallery__grid">';
      if (singlePost.source_url) {
        html += '<a class="ugc-gallery__item" href="' + singlePost.source_url + '" target="_blank" rel="noopener noreferrer">';
        html += '<img class="ugc-gallery__image" src="' + singlePost.image_url + '" alt="' + singleAlt + '" loading="lazy">';
        html += '</a>';
      } else {
        html += '<div class="ugc-gallery__item">';
        html += '<img class="ugc-gallery__image" src="' + singlePost.image_url + '" alt="' + singleAlt + '" loading="lazy">';
        html += '</div>';
      }
      html += '</div>';

      if (container) {
        container.innerHTML = html;
      }
      return;
    }

    // 2+ posts: carousel layout
    html += '<div class="ugc-carousel">';
    html += '<div class="ugc-carousel-track">';

    // Render original images
    for (var i = 0; i < sortedPosts.length; i++) {
      var post = sortedPosts[i];
      var imgAlt = t('ugc_gallery_title') + ' ' + (i + 1);
      html += '<img class="ugc-carousel__image" src="' + post.image_url + '" alt="' + imgAlt + '" loading="lazy">';
    }

    // Clone images for seamless infinite loop
    for (var j = 0; j < sortedPosts.length; j++) {
      var clonePost = sortedPosts[j];
      var cloneAlt = t('ugc_gallery_title') + ' ' + (j + 1);
      html += '<img class="ugc-carousel__image" src="' + clonePost.image_url + '" alt="' + cloneAlt + '" loading="lazy" aria-hidden="true">';
    }

    html += '</div>'; // .ugc-carousel-track
    html += '</div>'; // .ugc-carousel

    // Render into container
    if (container) {
      container.innerHTML = html;
    }

    // Initialize carousel animation (only if reduced motion is not preferred)
    var trackEl = container.querySelector('.ugc-carousel-track');
    if (!prefersReducedMotion()) {
      if (trackEl) {
        _activeCarousel = new UGCCarousel(trackEl, sortedPosts.length);
        _activeCarousel.start();
      }
    }

    // Listen for runtime changes to prefers-reduced-motion preference
    var motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    function handleReducedMotionChange(e) {
      if (e.matches) {
        // Reduced motion became active: stop animation, remove transform
        if (_activeCarousel) {
          _activeCarousel.stop();
        }
        if (trackEl) {
          trackEl.style.transform = '';
        }
      } else {
        // Reduced motion became inactive: start/restart the carousel
        if (trackEl) {
          if (_activeCarousel) {
            _activeCarousel.offset = 0;
            _activeCarousel.start();
          } else {
            _activeCarousel = new UGCCarousel(trackEl, sortedPosts.length);
            _activeCarousel.start();
          }
        }
      }
    }

    // Use addEventListener with 'change' event, with fallback to addListener for older browsers
    if (motionQuery.addEventListener) {
      motionQuery.addEventListener('change', handleReducedMotionChange);
    } else if (motionQuery.addListener) {
      motionQuery.addListener(handleReducedMotionChange);
    }
  }

  /**
   * Resolves override fields for a campaign product.
   * For each overridable field, uses the override value if present (non-null and non-empty),
   * otherwise falls back to the Product_Library default value.
   *
   * @param {Object} product - A campaign product object with optional override fields
   * @returns {Object} A new object with resolved values applied
   */
  function resolveProductOverrides(product) {
    if (!product) {
      return product;
    }

    var resolved = {};

    // Copy all fields from the original product
    var keys = Object.keys(product);
    for (var i = 0; i < keys.length; i++) {
      resolved[keys[i]] = product[keys[i]];
    }

    // Resolve override fields: use override if non-null and non-empty, otherwise use base value
    if (product.override_product_image_url) {
      resolved.product_image_url = product.override_product_image_url;
    }

    if (product.override_product_detail_url) {
      resolved.product_detail_url = product.override_product_detail_url;
    }

    if (product.override_size_guide_url) {
      resolved.size_guide_url = product.override_size_guide_url;
    }

    if (product.override_short_description) {
      resolved.short_description = product.override_short_description;
    }

    return resolved;
  }

  /**
   * Renders the product section based on product_mode.
   * Applies override resolution to each product before rendering.
   * @param {Object} config - The campaign configuration
   */
  function renderProducts(config) {
    if (!config.products || config.products.length === 0) {
      return;
    }

    // Resolve overrides for all products before rendering
    var resolvedProducts = [];
    for (var i = 0; i < config.products.length; i++) {
      resolvedProducts.push(resolveProductOverrides(config.products[i]));
    }

    if (config.product_mode === 'single') {
      renderSingleProduct(resolvedProducts[0]);
    } else if (config.product_mode === 'multiple') {
      renderMultipleProducts(resolvedProducts);
    }
  }

  /**
   * Checks if the campaign is currently active based on start_date and end_date.
   * Returns an object with { active: boolean, message: string|null }
   * @param {Object} config - The campaign configuration
   * @returns {{ active: boolean, message: string|null }}
   */
  function checkCampaignTimeLimit(config) {
    var now = new Date();

    if (config.start_date) {
      var startDate = new Date(config.start_date);
      if (now < startDate) {
        return { active: false, message: t('campaign_not_started') || '활동이 아직 시작되지 않았습니다.' };
      }
    }

    if (config.end_date) {
      var endDate = new Date(config.end_date);
      if (now > endDate) {
        return { active: false, message: t('campaign_ended') || '활동이 종료되었습니다.' };
      }
    }

    return { active: true, message: null };
  }

  /**
   * Renders a campaign expired/not-started overlay message.
   * Hides the form section and shows the message prominently.
   * @param {string} message - The message to display
   */
  function renderCampaignInactive(message) {
    var formSection = document.getElementById('form-section');
    if (formSection) {
      formSection.innerHTML = '<div class="campaign-inactive">' +
        '<div class="campaign-inactive__icon">⏰</div>' +
        '<p class="campaign-inactive__message">' + message + '</p>' +
        '</div>';
    }
  }

  /**
   * Main initialization function. Called on page load.
   * Extracts campaign ID, fetches config, initializes i18n, renders page.
   */
  function initCampaignPage() {
    var campaignId = getCampaignIdFromUrl();

    if (!campaignId) {
      console.error('[campaign] No campaign ID found in URL. Use ?campaign=<id>');
      return;
    }

    fetchCampaignConfig(campaignId)
      .then(function (config) {
        // Store config globally
        _campaignConfig = config;
        global.campaignConfig = config;

        // Initialize i18n with the campaign's market
        var market = config.market || 'ko';
        return I18n.init(market).then(function () {
          return config;
        });
      })
      .then(function (config) {
        // Render page sections
        renderHero(config);
        renderIntroduction(config);
        renderProducts(config);

        // Check campaign time limit before rendering form
        var timeCheck = checkCampaignTimeLimit(config);
        if (timeCheck.active) {
          renderForm(config);
        } else {
          renderCampaignInactive(timeCheck.message);
        }

        renderUGCGallery(config.ugc_gallery);
      })
      .catch(function (error) {
        console.error('[campaign] Failed to initialize campaign page:', error);
      });
  }

  /**
   * Shows a popup/modal with the size guide image.
   * @param {string} imageUrl - The size guide image URL or Base64 data
   */
  function showSizeGuidePopup(imageUrl) {
    if (!imageUrl) return;

    // Remove existing modal if present
    var existing = document.getElementById('size-guide-modal');
    if (existing) existing.parentNode.removeChild(existing);

    var html = '<div class="product-detail-modal" id="size-guide-modal" role="dialog" aria-modal="true" aria-label="사이즈 가이드">';
    html += '<div class="product-detail-modal__overlay" data-action="close-sg"></div>';
    html += '<div class="product-detail-modal__content" style="max-width:500px;padding:16px;">';
    html += '<button type="button" class="product-detail-modal__close" data-action="close-sg" aria-label="닫기">&times;</button>';
    html += '<h3 style="margin-bottom:12px;font-size:1.1rem;">' + t('size_guide_button') + '</h3>';
    html += '<img src="' + imageUrl + '" alt="사이즈 가이드" style="width:100%;height:auto;border-radius:8px;">';
    html += '</div></div>';

    var el = document.createElement('div');
    el.innerHTML = html;
    var modal = el.firstChild;
    document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';

    function closeModal() {
      var m = document.getElementById('size-guide-modal');
      if (m) m.parentNode.removeChild(m);
      document.body.style.overflow = '';
    }

    modal.addEventListener('click', function(e) {
      if (e.target.getAttribute('data-action') === 'close-sg') closeModal();
    });

    document.addEventListener('keydown', function handler(e) {
      if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', handler); }
    });
  }

  // Export to global scope
  global.Campaign = {
    init: initCampaignPage,
    getConfig: getCampaignConfig,
    getCampaignIdFromUrl: getCampaignIdFromUrl,
    fetchCampaignConfig: fetchCampaignConfig,
    resolveProductOverrides: resolveProductOverrides,
    truncateText: truncateText,
    isValidDisplayUrl: isValidDisplayUrl,
    renderSingleProduct: renderSingleProduct,
    renderMultipleProducts: renderMultipleProducts,
    renderForm: renderForm,
    renderUGCGallery: renderUGCGallery,
    selectProduct: selectProduct,
    getSelectedProductId: getSelectedProductId,
    showProductDetail: showProductDetail,
    UGCCarousel: UGCCarousel,
    prefersReducedMotion: prefersReducedMotion,
    checkCampaignTimeLimit: checkCampaignTimeLimit,
    showSizeGuidePopup: showSizeGuidePopup
  };

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCampaignPage);
  } else {
    initCampaignPage();
  }

})(typeof window !== 'undefined' ? window : this);
