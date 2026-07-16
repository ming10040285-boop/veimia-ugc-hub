/**
 * VEIMIA UGC Hub Admin Panel - Alpine.js Application
 * 
 * Root application state management using Alpine.js.
 * Each tab section (campaigns, products, UGC, settings) is managed
 * via reactive state and populated by subsequent tasks (8.2-8.6).
 */

function adminApp() {
  return {
    // Navigation state
    activeTab: 'campaigns',

    // Data collections
    campaigns: [],
    products: [],
    ugcPosts: [],

    // UI state flags
    showCreateCampaign: false,
    showCreateProduct: false,
    showAddUGC: false,
    isLoading: false,
    statusMessage: '',

    // Selected items
    selectedCampaignId: null,
    selectedProductId: null,

    // Mobile preview
    previewUrl: '/index.html',

    // Registration viewer state
    registrations: [],
    registrationsCount: 0,
    registrationsWarning: '',
    registrationsLoading: false,
    showRegistrations: false,

    // Campaign management state
    editingCampaign: null,
    assignedProducts: [],
    newCampaign: {
      campaign_id: '',
      campaign_name: '',
      product_mode: '',
      market: 'ko',
      hero_image_url: '',
      introduction_text: '',
      start_date_local: '',
      end_date_local: ''
    },
    createCampaignError: '',
    campaignError: '',
    campaignSuccess: '',

    // Drag-to-reorder state
    dragIndex: null,
    dragOverIndex: null,

    // Previous product_mode for mode-change detection
    _previousProductMode: null,

    /**
     * Initialize the admin application.
     * Loads initial data from config files.
     */
    async init() {
      this.statusMessage = '로딩 중...';
      try {
        this.loadSettings();
        await this.loadCampaigns();
        await this.loadProducts();
        this.statusMessage = '준비 완료';
      } catch (error) {
        console.error('Admin init error:', error);
        this.statusMessage = '데이터 로딩 실패';
      }
    },

    /**
     * Load campaigns list.
     * Tries API first, falls back to loading known campaign configs directly.
     */
    async loadCampaigns() {
      // Load directly from static config file (reliable across all deploy modes)
      try {
        const demoResp = await fetch('/config/campaigns/demo.json');
        if (demoResp.ok) {
          const demoData = await demoResp.json();
          this.campaigns = [demoData];
        } else {
          this.campaigns = [];
        }
      } catch (error) {
        console.error('Failed to load campaigns:', error);
        this.campaigns = [];
      }
    },

    /**
     * Load product library.
     * Tries API first, falls back to loading products/library.json directly.
     */
    async loadProducts() {
      try {
        const response = await fetch('/api/admin/products');
        if (response.ok) {
          const data = await response.json();
          // API returns {status: "success", data: [...]} 
          this.products = data.data || data.products || [];
          return;
        }
      } catch (error) {
        console.error('Products API error:', error);
      }

      // Fallback: load directly from config file (cached, may be stale)
      try {
        const resp = await fetch('/config/products/library.json');
        if (resp.ok) {
          const data = await resp.json();
          this.products = data.products || [];
        } else {
          this.products = [];
        }
      } catch (error) {
        console.error('Failed to load products:', error);
        this.products = [];
      }
    },

    /**
     * Load UGC posts for a specific campaign.
     * @param {string} campaignId - The campaign ID to load UGC for
     */
    async loadUGCPosts(campaignId) {
      if (!campaignId) {
        this.ugcPosts = [];
        return;
      }
      try {
        const response = await fetch(`/api/admin/ugc?campaign_id=${campaignId}`);
        if (response.ok) {
          const data = await response.json();
          this.ugcPosts = data.posts || [];
        }
      } catch (error) {
        console.error('Failed to load UGC posts:', error);
        this.ugcPosts = [];
      }
    },

    /**
     * Load registrations for a specific campaign from the admin API.
     * @param {string} campaignId - The campaign ID to load registrations for
     */
    async loadRegistrations(campaignId) {
      if (!campaignId) {
        this.registrations = [];
        this.registrationsCount = 0;
        this.registrationsWarning = '';
        return;
      }

      this.registrationsLoading = true;
      this.registrationsWarning = '';

      try {
        const response = await fetch(`/api/admin/registrations?campaign_id=${campaignId}`);
        if (response.ok) {
          const data = await response.json();
          this.registrations = data.registrations || [];
          this.registrationsCount = data.count || 0;
          this.registrationsWarning = data.warning || '';
        } else {
          this.registrations = [];
          this.registrationsCount = 0;
          this.registrationsWarning = '신청 데이터를 불러오는데 실패했습니다.';
        }
      } catch (error) {
        console.error('Failed to load registrations:', error);
        this.registrations = [];
        this.registrationsCount = 0;
        this.registrationsWarning = '네트워크 오류가 발생했습니다.';
      } finally {
        this.registrationsLoading = false;
      }
    },

    /**
     * Toggle registration section visibility and load data on demand
     */
    toggleRegistrations() {
      this.showRegistrations = !this.showRegistrations;
      if (this.showRegistrations && this.editingCampaign) {
        this.loadRegistrations(this.editingCampaign.campaign_id);
      }
    },

    /**
     * Refresh the mobile preview iframe.
     * Updates the iframe src to reflect the currently selected campaign.
     */
    refreshPreview() {
      const baseUrl = '/index.html';
      if (this.selectedCampaignId) {
        this.previewUrl = `${baseUrl}?campaign=${this.selectedCampaignId}`;
      } else {
        this.previewUrl = baseUrl;
      }
      // Force iframe reload by toggling src
      const iframe = document.querySelector('.preview-iframe');
      if (iframe) {
        iframe.src = this.previewUrl;
      }
    },

    /**
     * Select a campaign and update preview.
     * @param {string} campaignId - The campaign to select
     */
    selectCampaign(campaignId) {
      this.selectedCampaignId = campaignId;
      this.refreshPreview();
    },

    // =============================================
    // Campaign Management Methods
    // =============================================

    /**
     * Create a new campaign via POST /api/admin/campaigns
     */
    async createCampaign() {
      this.createCampaignError = '';

      // Validate required fields
      if (!this.newCampaign.campaign_name.trim()) {
        this.createCampaignError = '캠페인 이름을 입력해 주세요.';
        return;
      }
      if (!this.newCampaign.product_mode) {
        this.createCampaignError = '상품 모드를 선택해 주세요.';
        return;
      }

      // Build complete campaign object locally
      const campaignId = this.newCampaign.campaign_id.trim() || ('campaign-' + Date.now());
      const campaignData = {
        campaign_id: campaignId,
        campaign_name: this.newCampaign.campaign_name.trim(),
        product_mode: this.newCampaign.product_mode,
        market: this.newCampaign.market.trim() || 'ko',
        hero_image_url: this.newCampaign.hero_image_url || '',
        introduction_text: this.newCampaign.introduction_text.trim() || '',
        status: 'draft',
        start_date: this.newCampaign.start_date_local ? new Date(this.newCampaign.start_date_local).toISOString() : null,
        end_date: this.newCampaign.end_date_local ? new Date(this.newCampaign.end_date_local).toISOString() : null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        products: [],
        ugc_gallery: []
      };

      // Add to local list immediately (works without API)
      this.campaigns.push(campaignData);

      // Reset form and close modal
      this.newCampaign = {
        campaign_id: '',
        campaign_name: '',
        product_mode: '',
        market: 'ko',
        hero_image_url: '',
        introduction_text: '',
        start_date_local: '',
        end_date_local: ''
      };
      this.showCreateCampaign = false;

      // Auto-download the JSON for deployment
      const blob = new Blob([JSON.stringify(campaignData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = campaignId + '.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      this.statusMessage = '캠페인 생성 완료! JSON 파일을 config/campaigns/에 넣고 재배포하세요.';

      // Also try API in background (best-effort, don't block)
      try {
        const apiPayload = { ...campaignData };
        delete apiPayload.products;
        delete apiPayload.ugc_gallery;
        if (apiPayload.hero_image_url && apiPayload.hero_image_url.startsWith('data:')) {
          apiPayload.hero_image_url = '';
        }
        fetch('/api/admin/campaigns', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(apiPayload)
        }).catch(() => {});
      } catch (e) {}
    },

    /**
     * Open campaign edit view
     * @param {Object} campaign - Campaign object to edit
     */
    openCampaignEdit(campaign) {
      this.editingCampaign = { ...campaign };
      this._previousProductMode = campaign.product_mode;
      
      // Convert ISO dates to datetime-local format for input fields
      if (campaign.start_date) {
        this.editingCampaign.start_date_local = campaign.start_date.slice(0, 16);
      } else {
        this.editingCampaign.start_date_local = '';
      }
      if (campaign.end_date) {
        this.editingCampaign.end_date_local = campaign.end_date.slice(0, 16);
      } else {
        this.editingCampaign.end_date_local = '';
      }

      // Ensure all assigned products have override fields and _configExpanded state
      this.assignedProducts = (campaign.products ? [...campaign.products] : []).map(p => ({
        ...p,
        override_product_image_url: p.override_product_image_url || null,
        override_product_detail_url: p.override_product_detail_url || null,
        override_size_guide_url: p.override_size_guide_url || null,
        override_short_description: p.override_short_description || null,
        _configExpanded: false
      }));
      this.campaignError = '';
      this.campaignSuccess = '';
      this.selectCampaign(campaign.campaign_id);
    },

    /**
     * Close campaign edit view and return to list
     */
    closeCampaignEdit() {
      this.editingCampaign = null;
      this.assignedProducts = [];
      this.campaignError = '';
      this.campaignSuccess = '';
      this._previousProductMode = null;
      this.registrations = [];
      this.registrationsCount = 0;
      this.registrationsWarning = '';
      this.showRegistrations = false;
    },

    /**
     * Handle product_mode change - show confirmation if products are already assigned
     * @param {string} newMode - The new product_mode value
     */
    onProductModeChange(newMode) {
      if (this.assignedProducts.length > 0 && newMode !== this._previousProductMode) {
        const confirmed = confirm(
          '상품 모드를 변경하면 현재 배정된 상품이 모두 제거됩니다. 계속하시겠습니까?'
        );
        if (confirmed) {
          this.assignedProducts = [];
          this._previousProductMode = newMode;
        } else {
          // Revert selection
          this.editingCampaign.product_mode = this._previousProductMode;
        }
      } else {
        this._previousProductMode = newMode;
      }
    },

    /**
     * Check if a product is currently assigned
     * @param {string} productId
     * @returns {boolean}
     */
    isProductAssigned(productId) {
      return this.assignedProducts.some(p => p.product_id === productId);
    },

    /**
     * Toggle product assignment from picker
     * For single mode: replace; for multiple mode: add/remove
     * @param {Object} product - Product from library
     */
    toggleProductAssignment(product) {
      const mode = this.editingCampaign.product_mode;
      const isAssigned = this.isProductAssigned(product.product_id);

      if (mode === 'single') {
        if (isAssigned) {
          // Deselect
          this.assignedProducts = [];
        } else {
          // Replace with new selection (exactly 1 allowed)
          this.assignedProducts = [{
            product_id: product.product_id,
            product_name: product.product_name,
            product_image_url: product.product_image_url,
            short_description: product.short_description,
            product_detail_url: product.product_detail_url || null,
            size_guide_url: product.size_guide_url || null,
            available_sizes: product.available_sizes || [],
            available_colors: product.available_colors || [],
            status: 'open',
            display_order: 1,
            override_product_image_url: null,
            override_product_detail_url: null,
            override_size_guide_url: null,
            override_short_description: null,
            _configExpanded: false
          }];
        }
      } else if (mode === 'multiple') {
        if (isAssigned) {
          // Remove from assigned
          this.assignedProducts = this.assignedProducts.filter(p => p.product_id !== product.product_id);
        } else {
          // Add if under limit (max 50)
          if (this.assignedProducts.length >= 50) {
            this.campaignError = '최대 50개 상품까지 등록 가능합니다.';
            return;
          }
          this.assignedProducts.push({
            product_id: product.product_id,
            product_name: product.product_name,
            product_image_url: product.product_image_url,
            short_description: product.short_description,
            product_detail_url: product.product_detail_url || null,
            size_guide_url: product.size_guide_url || null,
            available_sizes: product.available_sizes || [],
            available_colors: product.available_colors || [],
            status: 'open',
            display_order: this.assignedProducts.length + 1,
            override_product_image_url: null,
            override_product_detail_url: null,
            override_size_guide_url: null,
            override_short_description: null,
            _configExpanded: false
          });
        }
      }
      this.campaignError = '';
    },

    /**
     * Remove an assigned product by index
     * @param {number} index
     */
    removeAssignedProduct(index) {
      this.assignedProducts.splice(index, 1);
      // Recalculate display_order
      this.assignedProducts.forEach((p, i) => {
        p.display_order = i + 1;
      });
    },

    // =============================================
    // Drag-to-Reorder (multiple mode)
    // =============================================

    dragStart(index) {
      this.dragIndex = index;
    },

    dragOver(index) {
      if (this.dragIndex === null || this.dragIndex === index) return;
      this.dragOverIndex = index;

      // Reorder the array
      const item = this.assignedProducts.splice(this.dragIndex, 1)[0];
      this.assignedProducts.splice(index, 0, item);
      this.dragIndex = index;

      // Update display_order
      this.assignedProducts.forEach((p, i) => {
        p.display_order = i + 1;
      });
    },

    dragEnd() {
      this.dragIndex = null;
      this.dragOverIndex = null;
    },

    // =============================================
    // Campaign Save/Publish
    // =============================================

    /**
     * Save campaign configuration (name, mode, market, hero, intro)
     */
    async saveCampaignConfig() {
      this.campaignError = '';
      this.campaignSuccess = '';

      // Build full campaign data
      const campaignData = {
        ...this.editingCampaign,
        products: this.assignedProducts.map((p, i) => ({
          product_id: p.product_id,
          product_name: p.product_name,
          product_image_url: p.product_image_url,
          short_description: p.short_description,
          product_detail_url: p.product_detail_url || null,
          size_guide_url: p.size_guide_url || null,
          available_sizes: p.available_sizes || [],
          available_colors: p.available_colors || [],
          status: p.status || 'open',
          display_order: i + 1,
          override_product_image_url: p.override_product_image_url || null,
          override_product_detail_url: p.override_product_detail_url || null,
          override_size_guide_url: p.override_size_guide_url || null,
          override_short_description: p.override_short_description || null
        })),
        ugc_gallery: this.editingCampaign.ugc_gallery || [],
        updated_at: new Date().toISOString()
      };

      // Remove internal fields
      delete campaignData.start_date_local;
      delete campaignData.end_date_local;
      delete campaignData._configExpanded;

      // Save via GitHub API (always save as demo.json for the main campaign)
      const savePath = 'public/config/campaigns/' + (this.editingCampaign.campaign_id || 'demo') + '.json';
      try {
        const response = await fetch('/api/admin/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            path: savePath,
            content: campaignData
          })
        });

        if (response.ok) {
          this.campaignSuccess = '저장 완료! 약 30초 후 전면 페이지에 반영됩니다.';
          // Update local state
          const idx = this.campaigns.findIndex(c => c.campaign_id === this.editingCampaign.campaign_id);
          if (idx >= 0) this.campaigns[idx] = campaignData;
        } else {
          const err = await response.json().catch(() => ({}));
          this.campaignError = err.message || '저장에 실패했습니다.';
        }
      } catch (error) {
        this.campaignError = '네트워크 오류: ' + (error.message || '저장 실패') + ' — 이미지가 너무 큰 경우 이미지 URL을 사용해 주세요.';
      }
    },

    /**
     * Save product assignment via PUT /api/admin/campaign_products
     */
    async saveProductAssignment() {
      this.campaignError = '';
      this.campaignSuccess = '';

      // Update products in editing campaign
      this.editingCampaign.products = this.assignedProducts.map((p, i) => ({
        product_id: p.product_id,
        product_name: p.product_name,
        product_image_url: p.product_image_url,
        short_description: p.short_description,
        product_detail_url: p.product_detail_url,
        size_guide_url: p.size_guide_url,
        available_sizes: p.available_sizes,
        available_colors: p.available_colors,
        status: p.status || 'open',
        display_order: i + 1,
        override_product_image_url: p.override_product_image_url || null,
        override_product_detail_url: p.override_product_detail_url || null,
        override_size_guide_url: p.override_size_guide_url || null,
        override_short_description: p.override_short_description || null
      }));

      // Save the full campaign (including products) via saveCampaignConfig
      await this.saveCampaignConfig();
    },

    /**
     * Publish campaign - validate products exist first
     */
    async publishCampaign() {
      this.campaignError = '';
      this.campaignSuccess = '';

      // Check if products are assigned
      if (this.assignedProducts.length === 0) {
        this.campaignError = '최소 1개의 상품을 등록해 주세요.';
        return;
      }

      try {
        const payload = {
          status: 'published'
        };

        const response = await fetch(`/api/admin/campaigns/${this.editingCampaign.campaign_id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (response.ok) {
          this.editingCampaign.status = 'published';
          this.campaignSuccess = '캠페인이 게시되었습니다.';
          await this.loadCampaigns();
        } else {
          const errorData = await response.json().catch(() => ({}));
          this.campaignError = errorData.message || '게시에 실패했습니다.';
        }
      } catch (error) {
        console.error('Publish campaign error:', error);
        this.campaignError = '네트워크 오류가 발생했습니다.';
      }
    },

    /**
     * Delete a campaign
     * @param {string} campaignId
     */
    async deleteCampaign(campaignId) {
      if (!confirm('이 캠페인을 삭제하시겠습니까?')) return;

      try {
        const response = await fetch(`/api/admin/campaigns/${campaignId}`, {
          method: 'DELETE'
        });

        if (response.ok) {
          await this.loadCampaigns();
        } else {
          console.error('Failed to delete campaign');
        }
      } catch (error) {
        console.error('Delete campaign error:', error);
      }
    },

    // =============================================
    // Product Library Management
    // =============================================

    // Product form state
    productForm: {
      isEditing: false,
      product_id: '',
      product_name: '',
      product_image_url: '',
      product_detail_url: '',
      size_guide_url: '',
      short_description: '',
      available_sizes: [],
      available_colors: [],
      _newSize: '',
      _newColor: ''
    },
    productFormErrors: {},
    productFormSuccess: '',

    /**
     * Open the create product modal with empty form
     */
    createProduct() {
      this.productForm = {
        isEditing: false,
        product_id: '',
        product_name: '',
        product_image_url: '',
        product_detail_url: '',
        size_guide_url: '',
        short_description: '',
        available_sizes: [],
        available_colors: [],
        _newSize: '',
        _newColor: ''
      };
      this.productFormErrors = {};
      this.productFormSuccess = '';
      this.showCreateProduct = true;
    },

    /**
     * Open the edit product modal with pre-populated form
     * @param {Object} product - Product object from library
     */
    editProduct(product) {
      this.productForm = {
        isEditing: true,
        product_id: product.product_id,
        product_name: product.product_name || '',
        product_image_url: product.product_image_url || '',
        product_detail_url: product.product_detail_url || '',
        size_guide_url: product.size_guide_url || '',
        short_description: product.short_description || '',
        available_sizes: [...(product.available_sizes || [])],
        available_colors: [...(product.available_colors || [])],
        _newSize: '',
        _newColor: ''
      };
      this.productFormErrors = {};
      this.productFormSuccess = '';
      this.showCreateProduct = true;
    },

    /**
     * Close the product modal
     */
    closeProductModal() {
      this.showCreateProduct = false;
      this.productFormErrors = {};
      this.productFormSuccess = '';
    },

    /**
     * Add a size tag to the product form
     * @param {string} size - Size value to add
     */
    addSize(size) {
      const trimmed = (size || '').trim();
      if (!trimmed) return;
      if (this.productForm.available_sizes.length >= 20) {
        this.productFormErrors = { ...this.productFormErrors, available_sizes: '최대 20개까지 설정 가능합니다.' };
        return;
      }
      if (this.productForm.available_sizes.includes(trimmed)) {
        this.productFormErrors = { ...this.productFormErrors, available_sizes: '이미 추가된 사이즈입니다.' };
        return;
      }
      this.productForm.available_sizes.push(trimmed);
      this.productForm._newSize = '';
      this.productFormErrors = { ...this.productFormErrors, available_sizes: '' };
    },

    /**
     * Remove a size tag by index
     * @param {number} index
     */
    removeSize(index) {
      this.productForm.available_sizes.splice(index, 1);
    },

    /**
     * Add a color tag to the product form
     * @param {string} color - Color value to add
     */
    addColor(color) {
      const trimmed = (color || '').trim();
      if (!trimmed) return;
      if (this.productForm.available_colors.length >= 30) {
        this.productFormErrors = { ...this.productFormErrors, available_colors: '최대 30개까지 설정 가능합니다.' };
        return;
      }
      if (this.productForm.available_colors.includes(trimmed)) {
        this.productFormErrors = { ...this.productFormErrors, available_colors: '이미 추가된 컬러입니다.' };
        return;
      }
      this.productForm.available_colors.push(trimmed);
      this.productForm._newColor = '';
      this.productFormErrors = { ...this.productFormErrors, available_colors: '' };
    },

    /**
     * Remove a color tag by index
     * @param {number} index
     */
    removeColor(index) {
      this.productForm.available_colors.splice(index, 1);
    },

    /**
     * Validate a URL field on blur
     * @param {string} field - Field name (product_detail_url or size_guide_url)
     */
    validateUrlField(field) {
      const value = this.productForm[field];
      if (!value || value.trim() === '') {
        this.productFormErrors = { ...this.productFormErrors, [field]: '' };
        return;
      }
      if (!this.isValidUrl(value)) {
        this.productFormErrors = { ...this.productFormErrors, [field]: 'http:// 또는 https://로 시작하는 유효한 URL을 입력하세요.' };
      } else if (value.length > 2048) {
        this.productFormErrors = { ...this.productFormErrors, [field]: 'URL은 최대 2048자까지 입력 가능합니다.' };
      } else {
        this.productFormErrors = { ...this.productFormErrors, [field]: '' };
      }
    },

    /**
     * Check if a URL is valid (http/https scheme, max 2048 chars)
     * @param {string} url
     * @returns {boolean}
     */
    isValidUrl(url) {
      if (!url || url.length > 2048) return false;
      // Only allow HTTPS URLs (no more Base64 data URLs)
      if (!url.startsWith('https://')) return false;
      try {
        const parsed = new URL(url);
        return parsed.protocol === 'http:' || parsed.protocol === 'https:';
      } catch {
        return false;
      }
    },

    /**
     * Upload product image via file picker
     * @param {Event} event - File input change event
     */
    async uploadProductImage(event) {
      const file = event.target.files[0];
      if (!file) return;

      // Validate format
      const validTypes = ['image/png', 'image/jpeg', 'image/webp'];
      if (!validTypes.includes(file.type)) {
        this.productFormErrors = { ...this.productFormErrors, imageUpload: 'PNG, JPG, WebP 형식만 지원합니다.' };
        event.target.value = '';
        return;
      }

      // Validate size (5MB max)
      const maxSize = 5 * 1024 * 1024;
      if (file.size > maxSize) {
        this.productFormErrors = { ...this.productFormErrors, imageUpload: '파일 크기는 최대 5MB까지 허용됩니다.' };
        event.target.value = '';
        return;
      }

      // Clear error
      this.productFormErrors = { ...this.productFormErrors, imageUpload: '' };

      // Upload to GitHub storage via upload_image endpoint
      const reader = new FileReader();
      reader.onload = async (e) => {
        const dataUrl = e.target.result;
        const base64 = dataUrl.split(',')[1];
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 30000);
          const response = await fetch('/api/admin/upload_image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: file.name, data: base64 }),
            signal: controller.signal
          });
          clearTimeout(timeoutId);
          if (response.ok) {
            const result = await response.json();
            this.productForm.product_image_url = result.image_url;
            this.productFormErrors = { ...this.productFormErrors, product_image_url: '' };
          } else {
            const err = await response.json().catch(() => ({}));
            this.productFormErrors = { ...this.productFormErrors, imageUpload: err.error || '업로드에 실패했습니다.' };
          }
        } catch (error) {
          if (error.name === 'AbortError') {
            this.productFormErrors = { ...this.productFormErrors, imageUpload: '업로드 시간이 초과되었습니다.' };
          } else {
            this.productFormErrors = { ...this.productFormErrors, imageUpload: '네트워크 오류가 발생했습니다.' };
          }
        }
      };
      reader.onerror = () => {
        this.productFormErrors = { ...this.productFormErrors, imageUpload: '파일 읽기에 실패했습니다.' };
      };
      reader.readAsDataURL(file);
      event.target.value = '';
    },

    /**
     * Validate and save product (create or update)
     */
    async saveProduct() {
      this.productFormErrors = {};
      this.productFormSuccess = '';

      // Validate required fields
      const errors = {};

      if (!this.productForm.product_name.trim()) {
        errors.product_name = '상품 이름을 입력해 주세요.';
      } else if (this.productForm.product_name.length > 200) {
        errors.product_name = '상품 이름은 최대 200자까지 입력 가능합니다.';
      }

      if (!this.productForm.product_image_url.trim()) {
        errors.product_image_url = '상품 이미지 URL을 입력하거나 이미지를 업로드해 주세요.';
      } else if (!this.isValidUrl(this.productForm.product_image_url)) {
        errors.product_image_url = 'http:// 또는 https://로 시작하는 유효한 URL을 입력하세요.';
      }

      if (!this.productForm.short_description.trim()) {
        errors.short_description = '간단 설명을 입력해 주세요.';
      } else if (this.productForm.short_description.length > 500) {
        errors.short_description = '간단 설명은 최대 500자까지 입력 가능합니다.';
      }

      // Validate optional URL fields
      if (this.productForm.product_detail_url.trim()) {
        if (!this.isValidUrl(this.productForm.product_detail_url)) {
          errors.product_detail_url = 'http:// 또는 https://로 시작하는 유효한 URL을 입력하세요.';
        } else if (this.productForm.product_detail_url.length > 2048) {
          errors.product_detail_url = 'URL은 최대 2048자까지 입력 가능합니다.';
        }
      }

      if (this.productForm.size_guide_url.trim()) {
        if (!this.isValidUrl(this.productForm.size_guide_url)) {
          errors.size_guide_url = 'http:// 또는 https://로 시작하는 유효한 URL을 입력하세요.';
        } else if (this.productForm.size_guide_url.length > 2048) {
          errors.size_guide_url = 'URL은 최대 2048자까지 입력 가능합니다.';
        }
      }

      // Validate sizes
      if (this.productForm.available_sizes.length === 0) {
        errors.available_sizes = '최소 1개의 사이즈를 추가해 주세요.';
      } else if (this.productForm.available_sizes.length > 20) {
        errors.available_sizes = '사이즈는 최대 20개까지 설정 가능합니다.';
      }

      // Validate colors
      if (this.productForm.available_colors.length === 0) {
        errors.available_colors = '최소 1개의 컬러를 추가해 주세요.';
      } else if (this.productForm.available_colors.length > 30) {
        errors.available_colors = '컬러는 최대 30개까지 설정 가능합니다.';
      }

      if (Object.keys(errors).length > 0) {
        this.productFormErrors = errors;
        return;
      }

      // Build payload
      const payload = {
        product_id: this.productForm.product_id || ('prod-' + Date.now()),
        product_name: this.productForm.product_name.trim(),
        product_image_url: this.productForm.product_image_url,
        product_detail_url: this.productForm.product_detail_url.trim() || null,
        size_guide_url: this.productForm.size_guide_url.trim() || null,
        short_description: this.productForm.short_description.trim(),
        available_sizes: this.productForm.available_sizes,
        available_colors: this.productForm.available_colors
      };

      // Save locally (works without API)
      if (this.productForm.isEditing) {
        const idx = this.products.findIndex(p => p.product_id === this.productForm.product_id);
        if (idx >= 0) this.products[idx] = payload;
      } else {
        this.products.push(payload);
      }

      this.productFormSuccess = this.productForm.isEditing ? '상품이 수정되었습니다.' : '상품이 등록되었습니다.';

      // Save to API (persistent GitHub storage)
      try {
        const apiPayload = { ...payload };
        const method = this.productForm.isEditing ? 'PUT' : 'POST';
        const response = await fetch('/api/admin/products', {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(apiPayload)
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          this.productFormSuccess = '';
          this.productFormErrors = { ...this.productFormErrors, general: err.message || '저장에 실패했습니다.' };
          return;
        }
      } catch (e) {
        this.productFormSuccess = '';
        this.productFormErrors = { ...this.productFormErrors, general: '네트워크 오류: ' + e.message };
        return;
      }

      setTimeout(() => { this.closeProductModal(); }, 1000);
    },

    // =============================================
    // Product Configuration Override Methods
    // =============================================

    /**
     * Toggle the expand/collapse state of a product's config panel
     * @param {number} index - Index in assignedProducts array
     */
    toggleProductConfig(index) {
      this.assignedProducts[index]._configExpanded = !this.assignedProducts[index]._configExpanded;
    },

    /**
     * Clear an override field, reverting to Product_Library default
     * @param {number} index - Index in assignedProducts array
     * @param {string} field - Override field name (e.g. 'override_product_image_url')
     */
    clearOverride(index, field) {
      this.assignedProducts[index][field] = null;
    },

    /**
     * Toggle product status between open and closed
     * @param {number} index - Index in assignedProducts array
     * @param {string} status - 'open' or 'closed'
     */
    toggleProductStatus(index, status) {
      this.assignedProducts[index].status = status;
    },

    /**
     * Get the library default value for a product field
     * Used as placeholder text in override inputs
     * @param {string} productId - Product ID to look up
     * @param {string} field - Field name (e.g. 'product_image_url')
     * @returns {string} Library default value or empty string
     */
    getLibraryDefault(productId, field) {
      const libraryProduct = this.products.find(p => p.product_id === productId);
      if (libraryProduct && libraryProduct[field]) {
        return libraryProduct[field];
      }
      return '';
    },

    // =============================================
    // UGC Gallery Management Methods
    // =============================================

    // UGC state
    ugcSelectedCampaignId: '',
    ugcError: '',
    ugcSuccess: '',
    ugcDragIndex: null,
    ugcDragOverIndex: null,
    newUGCPost: {
      source_url: '',
      image_url: ''
    },
    ugcFormError: '',
    ugcUploading: false,
    ugcUploadError: '',

    /**
     * Load UGC posts for the selected campaign in the UGC tab.
     * Uses local config file (no backend API needed for drag-deploy mode).
     */
    async loadUGCForCampaign() {
      this.ugcError = '';
      this.ugcSuccess = '';
      this.ugcPosts = [];

      if (!this.ugcSelectedCampaignId) {
        return;
      }

      try {
        // Load from read_campaign API (reads directly from GitHub, no cache)
        const response = await fetch(`/api/admin/read_campaign?id=${this.ugcSelectedCampaignId}`);
        if (response.ok) {
          const data = await response.json();
          this.ugcPosts = (data.ugc_gallery || []).sort((a, b) => (a.display_order || 0) - (b.display_order || 0));
        } else {
          this.ugcError = 'UGC 게시물을 불러오는데 실패했습니다. 캠페인 파일을 확인하세요.';
        }
      } catch (error) {
        console.error('Failed to load UGC posts:', error);
        this.ugcError = '네트워크 오류가 발생했습니다.';
      }
    },

    /**
     * Validate an Instagram URL.
     * Must start with https://www.instagram.com/p/ or https://instagram.com/p/
     * @param {string} url
     * @returns {boolean}
     */
    isValidInstagramUrl(url) {
      if (!url) return false;
      const trimmed = url.trim();
      return (
        trimmed.startsWith('https://www.instagram.com/p/') ||
        trimmed.startsWith('https://instagram.com/p/')
      );
    },

    /**
     * Validate that an image_url is a valid HTTPS URL.
     * Rejects data: URIs, Base64 patterns, and URLs exceeding 2048 characters.
     * @param {string} url - The image URL to validate
     * @returns {boolean} true if valid HTTPS URL, false otherwise
     */
    validateImageUrl(url) {
      if (!url) return false;

      // Enforce maximum 2048 character length
      if (url.length > 2048) return false;

      // Reject data: URIs
      if (url.toLowerCase().startsWith('data:')) return false;

      // Must start with https://
      if (!url.startsWith('https://')) return false;

      // Reject strings that contain raw Base64 patterns
      // Base64 strings are typically long stretches of alphanumeric characters with +, /, and =
      // A segment of 100+ consecutive Base64 chars without typical URL characters (., /, ?, &, =) suggests embedded Base64
      const base64Pattern = /[A-Za-z0-9+/]{100,}/;
      if (base64Pattern.test(url)) return false;

      return true;
    },

    /**
     * Add a UGC post to the local list.
     * Works without backend API — adds to in-memory array.
     * Use "Export JSON" to save changes to file.
     */
    async addUGCPost() {
      this.ugcFormError = '';
      this.ugcError = '';
      this.ugcSuccess = '';

      const sourceUrl = (this.newUGCPost.source_url || '').trim();
      const imageUrl = (this.newUGCPost.image_url || '').trim();

      // Validate: at least image_url must be provided
      if (!imageUrl) {
        this.ugcFormError = '이미지 URL을 입력해 주세요.';
        return;
      }

      // Validate Instagram URL format if provided
      if (sourceUrl && !this.isValidInstagramUrl(sourceUrl)) {
        this.ugcFormError = '유효하지 않은 Instagram URL입니다. https://www.instagram.com/p/ 또는 https://instagram.com/p/ 로 시작해야 합니다.';
        return;
      }

      // Validate image_url format (HTTPS only, no data: URIs or Base64)
      if (!this.validateImageUrl(imageUrl)) {
        this.ugcFormError = 'HTTPS URL만 허용됩니다. data: URI 또는 Base64 데이터는 사용할 수 없습니다.';
        return;
      }

      // Enforce 20-post maximum
      if (this.ugcPosts.length >= 20) {
        this.ugcFormError = '최대 20개의 UGC 게시물만 등록할 수 있습니다.';
        return;
      }

      // Add to local array (no API call)
      const newPost = {
        post_id: 'ugc-' + Date.now(),
        image_url: imageUrl,
        source_url: sourceUrl || null,
        display_order: this.ugcPosts.length + 1
      };

      this.ugcPosts.push(newPost);
      this.newUGCPost = { source_url: '', image_url: '' };
      this.showAddUGC = false;
      this.ugcSuccess = 'UGC 게시물이 추가되었습니다. 저장 중...';
      // Save to GitHub
      await this._saveUGCToGitHub();
    },

    /**
     * Remove a UGC post from the local list with confirmation.
     * @param {string} postId - The ID of the post to remove
     */
    async removeUGCPost(postId) {
      if (!confirm('이 UGC 게시물을 삭제하시겠습니까?')) return;

      this.ugcError = '';
      this.ugcSuccess = '';

      // Remove from local array (no API call)
      this.ugcPosts = this.ugcPosts.filter(p => (p.post_id || p.id) !== postId);
      
      // Update display_order
      this.ugcPosts.forEach((p, i) => { p.display_order = i + 1; });
      
      this.ugcSuccess = 'UGC 게시물이 삭제되었습니다. 저장 중...';
      // Save to GitHub
      await this._saveUGCToGitHub();
    },

    /**
     * Update display_order after reorder (no API call in drag-deploy mode).
     */
    async reorderUGCPosts() {
      this.ugcError = '';
      this.ugcSuccess = '';
      // Update display_order in local array
      this.ugcPosts.forEach((p, i) => { p.display_order = i + 1; });
      // Save to GitHub via save API
      await this._saveUGCToGitHub();
    },

    /**
     * Save current UGC posts to GitHub (updates the campaign's ugc_gallery in demo.json)
     */
    async _saveUGCToGitHub() {
      if (!this.ugcSelectedCampaignId) return;
      
      try {
        // Load the full campaign from read_campaign API (no cache)
        const resp = await fetch(`/api/admin/read_campaign?id=${this.ugcSelectedCampaignId}`);
        if (!resp.ok) {
          this.ugcError = '캠페인 데이터를 불러올 수 없습니다.';
          return;
        }
        const campaignData = await resp.json();
        
        // Update ugc_gallery
        campaignData.ugc_gallery = this.ugcPosts.map((p, i) => ({
          post_id: p.post_id || ('ugc-' + Date.now() + '-' + i),
          image_url: p.image_url,
          source_url: p.source_url || null,
          display_order: i + 1
        }));
        
        // Save via GitHub API
        const saveResp = await fetch('/api/admin/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            path: 'public/config/campaigns/' + this.ugcSelectedCampaignId + '.json',
            content: campaignData
          })
        });
        
        if (saveResp.ok) {
          this.ugcSuccess = 'UGC 갤러리가 저장되었습니다. 약 30초 후 전면 페이지에 반영됩니다.';
        } else {
          const err = await saveResp.json().catch(() => ({}));
          this.ugcError = err.message || 'UGC 저장에 실패했습니다.';
        }
      } catch (e) {
        this.ugcError = '네트워크 오류: ' + e.message;
      }
    },

    // UGC Drag-to-Reorder
    ugcDragStart(index) {
      this.ugcDragIndex = index;
    },

    ugcDragOver(index) {
      if (this.ugcDragIndex === null || this.ugcDragIndex === index) return;
      this.ugcDragOverIndex = index;

      // Reorder the array
      const item = this.ugcPosts.splice(this.ugcDragIndex, 1)[0];
      this.ugcPosts.splice(index, 0, item);
      this.ugcDragIndex = index;
    },

    ugcDragEnd() {
      this.ugcDragIndex = null;
      this.ugcDragOverIndex = null;
      // Auto-save reorder
      this.reorderUGCPosts();
    },

    /**
     * Move a UGC post up in the list (for accessibility / mobile).
     * @param {number} index
     */
    moveUGCPostUp(index) {
      if (index <= 0) return;
      const temp = this.ugcPosts[index];
      this.ugcPosts.splice(index, 1);
      this.ugcPosts.splice(index - 1, 0, temp);
      this.reorderUGCPosts();
    },

    /**
     * Move a UGC post down in the list (for accessibility / mobile).
     * @param {number} index
     */
    moveUGCPostDown(index) {
      if (index >= this.ugcPosts.length - 1) return;
      const temp = this.ugcPosts[index];
      this.ugcPosts.splice(index, 1);
      this.ugcPosts.splice(index + 1, 0, temp);
      this.reorderUGCPosts();
    },

    // =============================================
    // Settings Management
    // =============================================

    settings: {
      brand_name: 'VEIMIA',
      brand_url: 'https://www.veimia.com',
      logo_url: '',
      brand_color: '#d4a574',
      contact_email: '',
      consent_purpose: '',
      consent_data_types: '',
      consent_retention: '',
      consent_withdrawal: '',
      version: '1.0.0',
      deploy_url: 'https://veimia-ugc-hub.vercel.app',
      sheets_connected: false,
      sheets_id: ''
    },
    settingsSuccess: '',

    /**
     * Load settings from localStorage (persists across sessions in same browser)
     */
    loadSettings() {
      try {
        const saved = localStorage.getItem('veimia_ugc_settings');
        if (saved) {
          const parsed = JSON.parse(saved);
          this.settings = { ...this.settings, ...parsed };
        }
      } catch (e) {
        console.error('Failed to load settings:', e);
      }
    },

    /**
     * Save settings to localStorage
     */
    saveSettings() {
      this.settingsSuccess = '';
      try {
        localStorage.setItem('veimia_ugc_settings', JSON.stringify(this.settings));
        this.settingsSuccess = '설정이 저장되었습니다.';
        setTimeout(() => { this.settingsSuccess = ''; }, 3000);
      } catch (e) {
        console.error('Failed to save settings:', e);
      }
    },

    /**
     * Handle image upload for settings fields (logo etc)
     * @param {Event} event
     * @param {string} field - settings field to set
     */
    handleSettingsImageUpload(event, field) {
      const file = event.target.files[0];
      if (!file) return;

      const validTypes = ['image/png', 'image/jpeg', 'image/webp', 'image/svg+xml'];
      if (!validTypes.includes(file.type)) return;
      if (file.size > 2 * 1024 * 1024) return;

      const reader = new FileReader();
      reader.onload = (e) => {
        this.settings[field] = e.target.result;
      };
      reader.readAsDataURL(file);
      event.target.value = '';
    },

    /**
     * Export the current editing campaign as a complete JSON file.
     * Includes all config, products, and UGC gallery data.
     * User can replace demo.json with this file and re-deploy.
     */
    exportCampaignJson() {
      if (!this.editingCampaign) return;

      const campaignData = {
        campaign_id: this.editingCampaign.campaign_id,
        campaign_name: this.editingCampaign.campaign_name,
        product_mode: this.editingCampaign.product_mode,
        market: this.editingCampaign.market || 'ko',
        hero_image_url: this.editingCampaign.hero_image_url || '',
        introduction_text: this.editingCampaign.introduction_text || '',
        status: this.editingCampaign.status || 'published',
        start_date: this.editingCampaign.start_date || null,
        end_date: this.editingCampaign.end_date || null,
        created_at: this.editingCampaign.created_at || new Date().toISOString(),
        updated_at: new Date().toISOString(),
        products: this.assignedProducts.map((p, i) => ({
          product_id: p.product_id,
          product_name: p.product_name,
          product_image_url: p.product_image_url,
          short_description: p.short_description,
          product_detail_url: p.product_detail_url || null,
          size_guide_url: p.size_guide_url || null,
          available_sizes: p.available_sizes || [],
          available_colors: p.available_colors || [],
          status: p.status || 'open',
          display_order: i + 1,
          override_product_image_url: p.override_product_image_url || null,
          override_product_detail_url: p.override_product_detail_url || null,
          override_size_guide_url: p.override_size_guide_url || null,
          override_short_description: p.override_short_description || null
        })),
        ugc_gallery: (this.editingCampaign.ugc_gallery || []).map((p, i) => ({
          post_id: p.post_id || ('ugc-' + (i + 1)),
          image_url: p.image_url,
          source_url: p.source_url || null,
          display_order: i + 1
        }))
      };

      const blob = new Blob([JSON.stringify(campaignData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = (this.editingCampaign.campaign_id || 'campaign') + '.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      this.campaignSuccess = 'JSON 파일이 다운로드되었습니다. public/config/campaigns/ 폴더에 교체 후 재배포하세요.';
    },

    /**
     * Export all campaign configs as a single JSON file
     */
    exportAllConfig() {
      const allData = {
        settings: this.settings,
        campaigns: this.campaigns,
        products: this.products,
        exported_at: new Date().toISOString()
      };
      const blob = new Blob([JSON.stringify(allData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'veimia-ugc-hub-config-' + new Date().toISOString().slice(0, 10) + '.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },

    /**
     * Export just the settings as JSON
     */
    exportSettings() {
      const blob = new Blob([JSON.stringify(this.settings, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'veimia-settings.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },

    // =============================================
    // UGC Image Upload (via /api/admin/upload_image)
    // =============================================

    /**
     * Upload a UGC image to GitHub storage via the upload_image endpoint.
     * Reads the file as Base64, validates MIME type, and POSTs to the backend.
     * On success, sets image_url to the returned raw GitHub URL.
     * @param {Event} event - File input change event
     */
    async uploadUGCImage(event) {
      const file = event.target.files[0];
      if (!file) return;

      // Reset errors
      this.ugcUploadError = '';
      this.ugcFormError = '';

      // Validate MIME type
      const validTypes = ['image/png', 'image/jpeg', 'image/webp'];
      if (!validTypes.includes(file.type)) {
        this.ugcUploadError = '지원하지 않는 형식입니다. PNG, JPEG, WebP 파일만 업로드할 수 있습니다.';
        event.target.value = '';
        return;
      }

      // Set uploading state
      this.ugcUploading = true;
      this.ugcUploadError = '';

      try {
        // Read file as Base64
        const base64Data = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            // Strip the data URI prefix (e.g., "data:image/png;base64,")
            const dataUrl = e.target.result;
            const base64 = dataUrl.split(',')[1];
            resolve(base64);
          };
          reader.onerror = () => reject(new Error('파일 읽기에 실패했습니다.'));
          reader.readAsDataURL(file);
        });

        // POST to upload endpoint with 30-second timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000);

        const response = await fetch('/api/admin/upload_image', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename: file.name,
            data: base64Data
          }),
          signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
          const result = await response.json();
          this.newUGCPost.image_url = result.image_url;
        } else {
          const errorData = await response.json().catch(() => ({}));
          this.ugcUploadError = errorData.error || '업로드에 실패했습니다.';
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          this.ugcUploadError = '업로드 시간이 초과되었습니다. 다시 시도해 주세요.';
        } else {
          this.ugcUploadError = error.message || '네트워크 오류가 발생했습니다.';
        }
      } finally {
        this.ugcUploading = false;
        event.target.value = '';
      }
    },

    /**
     * Handle local image file upload for hero image in campaign edit.
     * Uploads to GitHub storage and stores URL.
     * @param {Event} event - File input change event
     */
    async handleHeroImageUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      const validTypes = ['image/png', 'image/jpeg', 'image/webp'];
      if (!validTypes.includes(file.type)) {
        this.campaignError = 'PNG, JPG, WebP 형식만 지원합니다.';
        event.target.value = '';
        return;
      }

      this.campaignError = '';
      const reader = new FileReader();
      reader.onload = async (e) => {
        const dataUrl = e.target.result;
        const base64 = dataUrl.split(',')[1];
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 30000);
          const response = await fetch('/api/admin/upload_image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: file.name, data: base64 }),
            signal: controller.signal
          });
          clearTimeout(timeoutId);
          if (response.ok) {
            const result = await response.json();
            this.editingCampaign.hero_image_url = result.image_url;
          } else {
            const err = await response.json().catch(() => ({}));
            this.campaignError = err.error || '업로드에 실패했습니다.';
          }
        } catch (error) {
          this.campaignError = error.name === 'AbortError' ? '업로드 시간이 초과되었습니다.' : '네트워크 오류가 발생했습니다.';
        }
      };
      reader.readAsDataURL(file);
      event.target.value = '';
    },

    /**
     * Handle hero image upload for the NEW campaign creation modal.
     * @param {Event} event - File input change event
     */
    handleNewCampaignHeroUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      const validTypes = ['image/png', 'image/jpeg', 'image/webp'];
      if (!validTypes.includes(file.type)) {
        this.createCampaignError = 'PNG, JPG, WebP 형식만 지원합니다.';
        event.target.value = '';
        return;
      }

      this.createCampaignError = '';
      const reader = new FileReader();
      reader.onload = async (e) => {
        const dataUrl = e.target.result;
        const base64 = dataUrl.split(',')[1];
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 30000);
          const response = await fetch('/api/admin/upload_image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: file.name, data: base64 }),
            signal: controller.signal
          });
          clearTimeout(timeoutId);
          if (response.ok) {
            const result = await response.json();
            this.newCampaign.hero_image_url = result.image_url;
          } else {
            const err = await response.json().catch(() => ({}));
            this.createCampaignError = err.error || '업로드에 실패했습니다.';
          }
        } catch (error) {
          this.createCampaignError = error.name === 'AbortError' ? '업로드 시간이 초과되었습니다.' : '네트워크 오류가 발생했습니다.';
        }
      };
      reader.readAsDataURL(file);
      event.target.value = '';
    },

    // =============================================
    // UGC Export (Drag-Deploy Mode)
    // =============================================

    /**
     * Export current UGC gallery as JSON file for download.
     * User replaces demo.json ugc_gallery with this content and re-deploys.
     */
    exportUGCJson() {
      const ugcData = this.ugcPosts.map((p, i) => ({
        post_id: p.post_id || ('ugc-' + (i + 1)),
        image_url: p.image_url,
        source_url: p.source_url || null,
        display_order: i + 1
      }));

      const jsonStr = JSON.stringify(ugcData, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'ugc_gallery_' + (this.ugcSelectedCampaignId || 'export') + '.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      this.ugcSuccess = 'JSON 파일이 다운로드되었습니다. demo.json의 ugc_gallery에 붙여넣기 후 재배포하세요.';
    },

    // =============================================
    // Utility Methods
    // =============================================

    /**
     * Format ISO date to readable Korean format
     * @param {string} isoDate
     * @returns {string}
     */
    formatDate(isoDate) {
      if (!isoDate) return '';
      try {
        const date = new Date(isoDate);
        return date.toLocaleDateString('ko-KR', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit'
        });
      } catch {
        return isoDate;
      }
    }
  };
}
