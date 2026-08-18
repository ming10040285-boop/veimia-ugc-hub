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

    // Creator CRM (protected APIs)
    creators: [],
    creatorsTotal: 0,
    creatorsLoading: false,
    creatorsError: '',
    creatorSearch: '',
    selectedCreator: null,
    candidates: [],
    candidatesTotal: 0,
    candidatesLoading: false,
    candidatesError: '',
    candidateSearch: '',
    candidateCampaignFilter: '',
    candidateStatusFilter: '',
    candidateForm: { campaign_id: '', instagram_username: '' },
    workflowParticipants: [],
    workflowLoading: false,
    workflowError: '',
    workflowCampaignId: '',
    workflowJobMessage: '',
    adminApiToken: sessionStorage.getItem('veimia_admin_api_token') || '',
    adminApiTokenDraft: sessionStorage.getItem('veimia_admin_api_token') || '',

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
    registrationImportLoading: false,
    registrationImportResult: '',
    registrationImportError: '',

    // Campaign Google Sheet connection state
    sheetConnectionLoading: false,
    sheetConnectionMessage: '',
    sheetConnectionOk: false,

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
      end_date_local: '',
      google_sheet: '',
      worksheet_name: 'Sheet1'
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
      this.statusMessage = '加载中...';
      try {
        this.loadSettings();
        await this.loadCampaigns();
        await this.loadProducts();
        this.statusMessage = '就绪';
      } catch (error) {
        console.error('Admin init error:', error);
        this.statusMessage = '数据加载失败';
      }
    },

    /**
     * Load campaigns list.
     * Tries API first, falls back to loading known campaign configs directly.
     */
    async loadCampaigns() {
      // Try API first
      try {
        const response = await fetch('/api/admin/campaigns');
        if (response.ok) {
          const data = await response.json();
          if (data.campaigns && data.campaigns.length > 0) {
            this.campaigns = data.campaigns;
            return;
          }
        }
      } catch (e) {}

      // Fallback: load campaign index file
      let knownIds = [];
      try {
        const indexResp = await fetch('/config/campaigns/index.json?t=' + Date.now());
        if (indexResp.ok) {
          knownIds = await indexResp.json();
        }
      } catch (e) {}

      // If no index, try common IDs
      if (knownIds.length === 0) {
        knownIds = ['demo', 'UGC-4'];
      }

      const campaigns = [];
      for (const id of knownIds) {
        try {
          const resp = await fetch('/config/campaigns/' + id + '.json?t=' + Date.now());
          if (resp.ok) {
            const data = await resp.json();
            campaigns.push(data);
          }
        } catch (e) {}
      }
      this.campaigns = campaigns;
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
          this.registrationsWarning = '加载申请数据失败。';
        }
      } catch (error) {
        console.error('Failed to load registrations:', error);
        this.registrations = [];
        this.registrationsCount = 0;
        this.registrationsWarning = '网络错误。';
      } finally {
        this.registrationsLoading = false;
      }
    },

    async importConfirmedRegistrations() {
      this.registrationImportError = '';
      this.registrationImportResult = '';
      this.restoreRememberedAdminLogin();
      if (!this.adminApiToken) {
        this.registrationImportError = '请先在“达人管理”中输入管理员访问码。';
        return;
      }
      if (!this.editingCampaign || this.registrationsCount === 0) {
        this.registrationImportError = '当前 Campaign 没有可导入的报名记录。';
        return;
      }
      const confirmed = confirm(
        `即将把当前 ${this.registrationsCount} 条报名视为“已人工确认通过筛选”并导入 Creator CRM。是否继续？`
      );
      if (!confirmed) return;

      this.registrationImportLoading = true;
      try {
        const result = await this.crmRequest(
          '/api/admin/participants?action=import_registrations',
          {
            method: 'POST',
            body: JSON.stringify({
              campaign_id: this.editingCampaign.campaign_id,
              confirmed_eligible: true
            })
          }
        );
        const data = result.data || {};
        this.registrationImportResult = [
          `导入完成：新建达人 ${data.creators_created || 0} 位`,
          `更新达人 ${data.creators_updated || 0} 位`,
          `新建参与记录 ${data.participants_created || 0} 条`,
          `更新参与记录 ${data.participants_updated || 0} 条`,
          `无效 ${data.invalid_count || 0} 条`,
          `合并重复 ${data.duplicates_collapsed || 0} 条`
        ].join('；');
        if ((data.invalid_rows || []).length > 0) {
          const details = data.invalid_rows.slice(0, 5)
            .map(item => `第 ${item.row} 行：${item.message}`)
            .join('；');
          this.registrationImportResult += `。${details}`;
        }
      } catch (error) {
        if (error.status === 401 || error.status === 403) {
          this.clearAdminApiToken();
          this.registrationImportError = '管理员访问码无效，请到“达人管理”重新登录。';
        } else {
          this.registrationImportError = error.message || '导入 Creator CRM 失败。';
        }
      } finally {
        this.registrationImportLoading = false;
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

    extractSpreadsheetId(value) {
      const raw = String(value || '').trim();
      if (!raw) return '';
      const marker = '/spreadsheets/d/';
      let id = raw;
      if (raw.includes(marker)) {
        id = raw.split(marker)[1].split('/')[0];
      }
      id = id.split('?')[0].split('#')[0].trim();
      return /^[A-Za-z0-9_-]+$/.test(id) ? id : '';
    },

    buildRegistrationStorage(sheetValue, worksheetName) {
      const spreadsheetId = this.extractSpreadsheetId(sheetValue);
      if (!spreadsheetId) return null;
      return {
        provider: 'google_sheets',
        spreadsheet_id: spreadsheetId,
        worksheet_name: String(worksheetName || 'Sheet1').trim() || 'Sheet1',
        schema_version: 2,
        mode: 'dedicated'
      };
    },

    /**
     * Create a new campaign via POST /api/admin/campaigns
     */
    async createCampaign() {
      this.createCampaignError = '';

      // Validate required fields
      if (!this.newCampaign.campaign_name.trim()) {
        this.createCampaignError = '请输入活动名称。';
        return;
      }
      if (!this.newCampaign.product_mode) {
        this.createCampaignError = '请选择商品模式。';
        return;
      }

      // Build complete campaign object locally
      const campaignId = this.newCampaign.campaign_id.trim() || ('campaign-' + Date.now());
      const registrationStorage = this.buildRegistrationStorage(
        this.newCampaign.google_sheet,
        this.newCampaign.worksheet_name
      );
      if (this.newCampaign.google_sheet.trim() && !registrationStorage) {
        this.createCampaignError = 'Google Sheet 链接或 ID 格式不正确。';
        return;
      }

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
        ugc_gallery: [],
        ...(registrationStorage ? { registration_storage: registrationStorage } : {})
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
        end_date_local: '',
        google_sheet: '',
        worksheet_name: 'Sheet1'
      };
      this.showCreateCampaign = false;

      this.statusMessage = '活动创建成功！';

      // Save campaign JSON to GitHub
      try {
        await fetch('/api/admin/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            path: 'public/config/campaigns/' + campaignId + '.json',
            content: campaignData
          })
        });
      } catch (e) {}

      // Update campaign index
      try {
        const allIds = this.campaigns.map(c => c.campaign_id);
        await fetch('/api/admin/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            path: 'public/config/campaigns/index.json',
            content: allIds
          })
        });
      } catch (e) {}

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
      const storage = campaign.registration_storage || {};
      const screening = campaign.candidate_screening || {};
      this.editingCampaign = {
        ...campaign,
        registration_storage: {
          provider: 'google_sheets',
          spreadsheet_id: storage.spreadsheet_id || storage.spreadsheet_url || '',
          worksheet_name: storage.worksheet_name || 'Sheet1',
          schema_version: 2,
          mode: storage.spreadsheet_id || storage.spreadsheet_url ? 'dedicated' : 'legacy_shared'
        },
        candidate_screening: {
          schema_version: 1,
          execution_mode: 'manual',
          min_follower_count: screening.min_follower_count ?? null,
          max_follower_count: screening.max_follower_count ?? null,
          allow_private_accounts: screening.allow_private_accounts === true,
          max_days_since_last_post: screening.max_days_since_last_post ?? null
        }
      };
      this.sheetConnectionMessage = '';
      this.sheetConnectionOk = false;
      this.registrationImportLoading = false;
      this.registrationImportResult = '';
      this.registrationImportError = '';
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
      this.registrationImportLoading = false;
      this.registrationImportResult = '';
      this.registrationImportError = '';
      this.showRegistrations = false;
    },

    /**
     * Handle product_mode change - show confirmation if products are already assigned
     * @param {string} newMode - The new product_mode value
     */
    onProductModeChange(newMode) {
      if (this.assignedProducts.length > 0 && newMode !== this._previousProductMode) {
        const confirmed = confirm(
          '切换商品模式将移除当前已分配的所有商品。是否继续？'
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
            this.campaignError = '最多可分配 50 个商品。';
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

    async testCampaignSheet(initialize = false) {
      const storage = this.editingCampaign && this.editingCampaign.registration_storage;
      const spreadsheetId = this.extractSpreadsheetId(storage && storage.spreadsheet_id);
      if (!spreadsheetId) {
        this.sheetConnectionOk = false;
        this.sheetConnectionMessage = '请先填写有效的 Google Sheet 链接或 ID。';
        return;
      }

      this.sheetConnectionLoading = true;
      this.sheetConnectionMessage = initialize ? '正在初始化表头...' : '正在测试连接...';
      try {
        const response = await fetch('/api/admin/campaign-sheet', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: initialize ? 'initialize' : 'test',
            spreadsheet_id: spreadsheetId,
            worksheet_name: storage.worksheet_name || 'Sheet1'
          })
        });
        const data = await response.json().catch(() => ({}));
        this.sheetConnectionOk = response.ok;
        this.sheetConnectionMessage = data.message || (response.ok ? '表格连接成功。' : '表格连接失败。');
      } catch (error) {
        this.sheetConnectionOk = false;
        this.sheetConnectionMessage = '网络错误：' + (error.message || '连接失败');
      } finally {
        this.sheetConnectionLoading = false;
      }
    },

    /**
     * Save campaign configuration (name, mode, market, hero, intro)
     */
    async saveCampaignConfig() {
      this.campaignError = '';
      this.campaignSuccess = '';

      const storageInput = this.editingCampaign.registration_storage || {};
      const registrationStorage = this.buildRegistrationStorage(
        storageInput.spreadsheet_id,
        storageInput.worksheet_name
      );
      if (String(storageInput.spreadsheet_id || '').trim() && !registrationStorage) {
        this.campaignError = 'Google Sheet 链接或 ID 格式不正确。';
        return;
      }

      const rawScreening = this.editingCampaign.candidate_screening || {};
      const normalizeOptionalInteger = (value) => {
        if (value === '' || value === null || value === undefined) return null;
        const number = Number(value);
        return Number.isInteger(number) && number >= 0 ? number : NaN;
      };
      const minimumFollowers = normalizeOptionalInteger(rawScreening.min_follower_count);
      const maximumFollowers = normalizeOptionalInteger(rawScreening.max_follower_count);
      const maximumInactiveDays = normalizeOptionalInteger(rawScreening.max_days_since_last_post);
      if ([minimumFollowers, maximumFollowers, maximumInactiveDays].some(Number.isNaN)) {
        this.campaignError = '候选筛选规则只能填写非负整数，或留空关闭该规则。';
        return;
      }
      if (minimumFollowers !== null && maximumFollowers !== null && minimumFollowers > maximumFollowers) {
        this.campaignError = '最低粉丝数不能大于最高粉丝数。';
        return;
      }
      const candidateScreening = {
        schema_version: 1,
        execution_mode: 'manual',
        min_follower_count: minimumFollowers,
        max_follower_count: maximumFollowers,
        allow_private_accounts: rawScreening.allow_private_accounts === true,
        max_days_since_last_post: maximumInactiveDays
      };

      // Build full campaign data
      const campaignData = {
        ...this.editingCampaign,
        candidate_screening: candidateScreening,
        ...(registrationStorage ? { registration_storage: registrationStorage } : {}),
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
      if (!registrationStorage) delete campaignData.registration_storage;

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
          this.campaignSuccess = '保存成功！约 30 秒后前端页面将更新。';
          // Update local state
          const idx = this.campaigns.findIndex(c => c.campaign_id === this.editingCampaign.campaign_id);
          if (idx >= 0) this.campaigns[idx] = campaignData;
        } else {
          const err = await response.json().catch(() => ({}));
          this.campaignError = err.message || '保存失败。';
        }
      } catch (error) {
        this.campaignError = '网络错误: ' + (error.message || '保存失败') + ' — 如图片过大，请使用图片 URL。';
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
        this.campaignError = '请至少分配 1 个商品。';
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
          this.campaignSuccess = '活动已发布。';
          await this.loadCampaigns();
        } else {
          const errorData = await response.json().catch(() => ({}));
          this.campaignError = errorData.message || '发布失败。';
        }
      } catch (error) {
        console.error('Publish campaign error:', error);
        this.campaignError = '网络错误。';
      }
    },

    /**
     * Set the current campaign as the active one displayed on the homepage.
     * Updates /public/config/current.json via the save API.
     */
    async setAsCurrentCampaign() {
      this.campaignError = '';
      this.campaignSuccess = '';

      if (!this.editingCampaign || !this.editingCampaign.campaign_id) return;

      try {
        const response = await fetch('/api/admin/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            path: 'public/config/current.json',
            content: { campaign_id: this.editingCampaign.campaign_id }
          })
        });

        if (response.ok) {
          this.campaignSuccess = '已设为当前活动！前端首页将展示此活动（约 30 秒后生效）。';
        } else {
          const err = await response.json().catch(() => ({}));
          this.campaignError = err.message || '设置失败。';
        }
      } catch (error) {
        this.campaignError = '网络错误: ' + (error.message || '设置失败');
      }
    },

    /**
     * Delete a campaign
     * @param {string} campaignId
     */
    async deleteCampaign(campaignId) {
      if (!confirm('确定删除该活动吗？')) return;

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
        this.productFormErrors = { ...this.productFormErrors, available_sizes: '最多可设置 20 个。' };
        return;
      }
      if (this.productForm.available_sizes.includes(trimmed)) {
        this.productFormErrors = { ...this.productFormErrors, available_sizes: '该尺码已添加。' };
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
        this.productFormErrors = { ...this.productFormErrors, available_colors: '最多可设置 30 个。' };
        return;
      }
      if (this.productForm.available_colors.includes(trimmed)) {
        this.productFormErrors = { ...this.productFormErrors, available_colors: '该颜色已添加。' };
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
        this.productFormErrors = { ...this.productFormErrors, [field]: '请输入以 http:// 或 https:// 开头的有效 URL。' };
      } else if (value.length > 2048) {
        this.productFormErrors = { ...this.productFormErrors, [field]: 'URL 最长 2048 个字符。' };
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
        this.productFormErrors = { ...this.productFormErrors, imageUpload: '仅支持 PNG、JPG、WebP 格式。' };
        event.target.value = '';
        return;
      }

      // Validate size (5MB max)
      const maxSize = 5 * 1024 * 1024;
      if (file.size > maxSize) {
        this.productFormErrors = { ...this.productFormErrors, imageUpload: '文件大小不能超过 5MB。' };
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
            this.productFormErrors = { ...this.productFormErrors, imageUpload: err.error || '上传失败。' };
          }
        } catch (error) {
          if (error.name === 'AbortError') {
            this.productFormErrors = { ...this.productFormErrors, imageUpload: '上传超时。' };
          } else {
            this.productFormErrors = { ...this.productFormErrors, imageUpload: '网络错误。' };
          }
        }
      };
      reader.onerror = () => {
        this.productFormErrors = { ...this.productFormErrors, imageUpload: '文件读取失败。' };
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
        errors.product_name = '请输入商品名称。';
      } else if (this.productForm.product_name.length > 200) {
        errors.product_name = '商品名称最多 200 个字符。';
      }

      if (!this.productForm.product_image_url.trim()) {
        errors.product_image_url = '请输入商品图片 URL 或上传图片。';
      } else if (!this.isValidUrl(this.productForm.product_image_url)) {
        errors.product_image_url = '请输入以 http:// 或 https:// 开头的有效 URL。';
      }

      if (!this.productForm.short_description.trim()) {
        errors.short_description = '请输入简短描述。';
      } else if (this.productForm.short_description.length > 500) {
        errors.short_description = '简短描述最多 500 个字符。';
      }

      // Validate optional URL fields
      if (this.productForm.product_detail_url.trim()) {
        if (!this.isValidUrl(this.productForm.product_detail_url)) {
          errors.product_detail_url = '请输入以 http:// 或 https:// 开头的有效 URL。';
        } else if (this.productForm.product_detail_url.length > 2048) {
          errors.product_detail_url = 'URL 最长 2048 个字符。';
        }
      }

      if (this.productForm.size_guide_url.trim()) {
        if (!this.isValidUrl(this.productForm.size_guide_url)) {
          errors.size_guide_url = '请输入以 http:// 或 https:// 开头的有效 URL。';
        } else if (this.productForm.size_guide_url.length > 2048) {
          errors.size_guide_url = 'URL 最长 2048 个字符。';
        }
      }

      // Validate sizes
      if (this.productForm.available_sizes.length === 0) {
        errors.available_sizes = '请至少添加 1 个尺码。';
      } else if (this.productForm.available_sizes.length > 20) {
        errors.available_sizes = '尺码最多 20 个。';
      }

      // Validate colors
      if (this.productForm.available_colors.length === 0) {
        errors.available_colors = '请至少添加 1 个颜色。';
      } else if (this.productForm.available_colors.length > 30) {
        errors.available_colors = '颜色最多 30 个。';
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

      this.productFormSuccess = this.productForm.isEditing ? '商品已修改。' : '商品已添加。';

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
          this.productFormErrors = { ...this.productFormErrors, general: err.message || '保存失败。' };
          return;
        }
      } catch (e) {
        this.productFormSuccess = '';
        this.productFormErrors = { ...this.productFormErrors, general: '网络错误: ' + e.message };
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
          this.ugcError = '加载 UGC 帖子失败，请检查活动文件。';
        }
      } catch (error) {
        console.error('Failed to load UGC posts:', error);
        this.ugcError = '网络错误。';
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
        this.ugcFormError = '请输入图片 URL。';
        return;
      }

      // Validate Instagram URL format if provided
      if (sourceUrl && !this.isValidInstagramUrl(sourceUrl)) {
        this.ugcFormError = '无效的 Instagram URL。 必须以 https://www.instagram.com/p/ 或 https://instagram.com/p/ 开头。';
        return;
      }

      // Validate image_url format (HTTPS only, no data: URIs or Base64)
      if (!this.validateImageUrl(imageUrl)) {
        this.ugcFormError = '仅允许 HTTPS URL，不支持 data: URI 或 Base64 数据。';
        return;
      }

      // Enforce 20-post maximum
      if (this.ugcPosts.length >= 20) {
        this.ugcFormError = '最多可添加 20 条 UGC 帖子。';
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
      this.ugcSuccess = 'UGC 帖子已添加，保存中...';
      // Save to GitHub
      await this._saveUGCToGitHub();
    },

    /**
     * Remove a UGC post from the local list with confirmation.
     * @param {string} postId - The ID of the post to remove
     */
    async removeUGCPost(postId) {
      if (!confirm('确定删除该 UGC 帖子吗？')) return;

      this.ugcError = '';
      this.ugcSuccess = '';

      // Remove from local array (no API call)
      this.ugcPosts = this.ugcPosts.filter(p => (p.post_id || p.id) !== postId);
      
      // Update display_order
      this.ugcPosts.forEach((p, i) => { p.display_order = i + 1; });
      
      this.ugcSuccess = 'UGC 帖子已删除，保存中...';
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
          this.ugcError = '无法加载活动数据。';
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
          this.ugcSuccess = 'UGC 画廊已保存，约 30 秒后前端页面将更新。';
        } else {
          const err = await saveResp.json().catch(() => ({}));
          this.ugcError = err.message || 'UGC 保存失败。';
        }
      } catch (e) {
        this.ugcError = '网络错误: ' + e.message;
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
        this.settingsSuccess = '设置已保存。';
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

      this.campaignSuccess = 'JSON 文件已下载。请替换 public/config/campaigns/ 文件夹中的对应文件后重新部署。';
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
        this.ugcUploadError = '不支持该格式。仅可上传 PNG、JPEG、WebP 文件。';
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
          reader.onerror = () => reject(new Error('文件读取失败。'));
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
          this.ugcUploadError = errorData.error || '上传失败。';
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          this.ugcUploadError = '上传超时，请重试。';
        } else {
          this.ugcUploadError = error.message || '网络错误。';
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
        this.campaignError = '仅支持 PNG、JPG、WebP 格式。';
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
            this.campaignError = err.error || '上传失败。';
          }
        } catch (error) {
          this.campaignError = error.name === 'AbortError' ? '上传超时。' : '网络错误。';
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
        this.createCampaignError = '仅支持 PNG、JPG、WebP 格式。';
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
            this.createCampaignError = err.error || '上传失败。';
          }
        } catch (error) {
          this.createCampaignError = error.name === 'AbortError' ? '上传超时。' : '网络错误。';
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
      
      this.ugcSuccess = 'JSON 文件已下载。请将内容粘贴到 demo.json 的 ugc_gallery 字段后重新部署。';
    },

    // =============================================
    // Candidate Screening
    // =============================================

    openCandidatesTab() {
      this.activeTab = 'candidates';
      this.restoreRememberedAdminLogin();
      if (!this.candidateForm.campaign_id && this.campaigns.length > 0) {
        this.candidateForm.campaign_id = this.campaigns[0].campaign_id;
      }
      if (this.adminApiToken) this.loadCandidates();
    },

    async loadCandidates() {
      this.restoreRememberedAdminLogin();
      if (!this.adminApiToken) return;
      this.candidatesLoading = true;
      this.candidatesError = '';
      try {
        const query = new URLSearchParams({ limit: '200' });
        if (this.candidateSearch.trim()) query.set('q', this.candidateSearch.trim());
        if (this.candidateCampaignFilter) query.set('campaign_id', this.candidateCampaignFilter);
        if (this.candidateStatusFilter) query.set('screening_status', this.candidateStatusFilter);
        const result = await this.crmRequest('/api/admin/candidates?' + query.toString());
        this.candidates = result.data || [];
        this.candidatesTotal = result.page ? result.page.total : this.candidates.length;
      } catch (error) {
        this.candidates = [];
        this.candidatesTotal = 0;
        this.candidatesError = error.message || '加载候选达人失败。';
        if (error.status === 401 || error.status === 403) {
          this.clearAdminApiToken();
          this.candidatesError = '管理员访问码无效，请到“达人管理”重新登录。';
        }
      } finally {
        this.candidatesLoading = false;
      }
    },

    async createCandidate() {
      this.candidatesError = '';
      this.restoreRememberedAdminLogin();
      if (!this.adminApiToken) {
        this.candidatesError = '请先在“达人管理”中输入管理员访问码。';
        return;
      }
      if (!this.candidateForm.campaign_id || !this.candidateForm.instagram_username.trim()) {
        this.candidatesError = '请选择 Campaign 并填写 Instagram 用户名或主页链接。';
        return;
      }
      this.candidatesLoading = true;
      try {
        await this.crmRequest('/api/admin/candidates', {
          method: 'POST',
          body: JSON.stringify(this.candidateForm)
        });
        this.candidateForm.instagram_username = '';
        await this.loadCandidates();
      } catch (error) {
        this.candidatesError = error.message || '添加候选达人失败。';
      } finally {
        this.candidatesLoading = false;
      }
    },

    async editCandidateProfile(candidate) {
      const followerInput = prompt(
        '请输入粉丝数（非负整数）：',
        candidate.follower_count === null ? '' : String(candidate.follower_count)
      );
      if (followerInput === null) return;
      const followerCount = Number(followerInput);
      if (!Number.isInteger(followerCount) || followerCount < 0) {
        this.candidatesError = '粉丝数必须是非负整数。';
        return;
      }

      const privacyInput = prompt(
        '请输入“公开”或“私密”：',
        candidate.is_private === null ? '' : (candidate.is_private ? '私密' : '公开')
      );
      if (privacyInput === null) return;
      const privacy = privacyInput.trim();
      if (!['公开', '私密'].includes(privacy)) {
        this.candidatesError = '账号状态只能填写“公开”或“私密”。';
        return;
      }

      const currentDate = candidate.last_post_at ? candidate.last_post_at.slice(0, 10) : '';
      const lastPostInput = prompt('请输入最近发帖日期（YYYY-MM-DD）：', currentDate);
      if (lastPostInput === null) return;
      const lastPost = new Date(lastPostInput.trim() + 'T00:00:00Z');
      if (!/^\d{4}-\d{2}-\d{2}$/.test(lastPostInput.trim()) || Number.isNaN(lastPost.getTime())) {
        this.candidatesError = '最近发帖日期格式应为 YYYY-MM-DD。';
        return;
      }

      this.candidatesError = '';
      try {
        const result = await this.crmRequest(
          '/api/admin/candidates?candidate_id=' + encodeURIComponent(candidate.candidate_id),
          {
            method: 'PATCH',
            body: JSON.stringify({
              follower_count: followerCount,
              is_private: privacy === '私密',
              last_post_at: lastPost.toISOString(),
              profile_check_status: 'success'
            })
          }
        );
        const index = this.candidates.findIndex(item => item.candidate_id === candidate.candidate_id);
        if (index >= 0) this.candidates[index] = result.data;
      } catch (error) {
        this.candidatesError = error.message || '保存候选人资料失败。';
      }
    },

    async evaluateCandidate(candidate) {
      if (candidate.screening_status === 'promoted') return;
      if (!confirm(`确认按 @${candidate.instagram_username} 所属 Campaign 的规则执行筛选？`)) return;
      this.candidatesError = '';
      try {
        const result = await this.crmRequest('/api/admin/candidates?action=evaluate', {
          method: 'POST',
          body: JSON.stringify({ candidate_id: candidate.candidate_id })
        });
        const index = this.candidates.findIndex(item => item.candidate_id === candidate.candidate_id);
        if (index >= 0) this.candidates[index] = result.data;
      } catch (error) {
        this.candidatesError = error.message || '按规则评估候选人失败。';
      }
    },

    async updateCandidateStatus(candidate, status) {
      let reason = '';
      if (status === 'manual_review' || status === 'filtered') {
        reason = prompt(status === 'filtered' ? '请输入过滤原因：' : '请输入需要人工确认的原因：') || '';
        if (!reason.trim()) return;
      }
      this.candidatesError = '';
      try {
        const result = await this.crmRequest(
          '/api/admin/candidates?candidate_id=' + encodeURIComponent(candidate.candidate_id),
          {
            method: 'PATCH',
            body: JSON.stringify({ screening_status: status, screening_reason: reason || null })
          }
        );
        const index = this.candidates.findIndex(item => item.candidate_id === candidate.candidate_id);
        if (index >= 0) this.candidates[index] = result.data;
      } catch (error) {
        this.candidatesError = error.message || '更新候选人状态失败。';
      }
    },

    async promoteCandidate(candidate) {
      if (candidate.screening_status !== 'eligible') return;
      if (!confirm(`确认将 @${candidate.instagram_username} 加入 Creator CRM？`)) return;
      this.candidatesError = '';
      try {
        await this.crmRequest('/api/admin/candidates?action=promote', {
          method: 'POST',
          body: JSON.stringify({ candidate_id: candidate.candidate_id })
        });
        await this.loadCandidates();
      } catch (error) {
        this.candidatesError = error.message || '加入 Creator CRM 失败。';
      }
    },

    candidateStatusLabel(status) {
      return ({
        pending: '待筛选', eligible: '符合条件', manual_review: '待人工确认',
        filtered: '已过滤', promoted: '已进入 CRM'
      })[status] || status || '—';
    },

    // =============================================
    // Creator CRM
    // =============================================

    restoreRememberedAdminLogin() {
      if (this.adminApiToken) return;
      try {
        const token = localStorage.getItem('veimia_admin_api_token_remembered') || '';
        const expiresAt = Number(localStorage.getItem('veimia_admin_api_token_expires') || 0);
        if (!token || expiresAt <= Date.now()) {
          localStorage.removeItem('veimia_admin_api_token_remembered');
          localStorage.removeItem('veimia_admin_api_token_expires');
          return;
        }
        this.adminApiToken = token;
        this.adminApiTokenDraft = token;
        sessionStorage.setItem('veimia_admin_api_token', token);
      } catch {
        // Persistent storage may be unavailable in private browsing mode.
      }
    },

    openCreatorsTab() {
      this.activeTab = 'creators';
      this.selectedCreator = null;
      this.restoreRememberedAdminLogin();
      if (this.adminApiToken) this.loadCreators();
    },

    saveAdminApiToken() {
      const token = String(this.adminApiTokenDraft || '').trim();
      if (!token) {
        this.creatorsError = '请输入管理员访问码。';
        return;
      }
      this.adminApiToken = token;
      sessionStorage.setItem('veimia_admin_api_token', token);
      try {
        if (this.$refs.rememberAdminLogin && this.$refs.rememberAdminLogin.checked) {
          const thirtyDays = 30 * 24 * 60 * 60 * 1000;
          localStorage.setItem('veimia_admin_api_token_remembered', token);
          localStorage.setItem('veimia_admin_api_token_expires', String(Date.now() + thirtyDays));
        } else {
          localStorage.removeItem('veimia_admin_api_token_remembered');
          localStorage.removeItem('veimia_admin_api_token_expires');
        }
      } catch {
        // The current session still works when persistent storage is unavailable.
      }
      this.creatorsError = '';
      this.loadCreators();
    },

    clearAdminApiToken() {
      this.adminApiToken = '';
      this.adminApiTokenDraft = '';
      this.creators = [];
      this.creatorsTotal = 0;
      this.selectedCreator = null;
      this.candidates = [];
      this.candidatesTotal = 0;
      this.candidatesError = '';
      this.workflowParticipants = [];
      this.workflowError = '';
      this.workflowJobMessage = '';
      this.creatorsError = '';
      sessionStorage.removeItem('veimia_admin_api_token');
      try {
        localStorage.removeItem('veimia_admin_api_token_remembered');
        localStorage.removeItem('veimia_admin_api_token_expires');
      } catch {
        // Ignore storage cleanup failures.
      }
    },

    async crmRequest(url, options = {}) {
      const headers = {
        'Authorization': 'Bearer ' + this.adminApiToken,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {})
      };
      const response = await fetch(url, { ...options, headers });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error(data.message || '达人数据库请求失败。');
        error.status = response.status;
        throw error;
      }
      return data;
    },

    async loadCreators() {
      if (!this.adminApiToken) return;
      this.creatorsLoading = true;
      this.creatorsError = '';
      try {
        const query = new URLSearchParams({ limit: '100' });
        if (this.creatorSearch.trim()) query.set('q', this.creatorSearch.trim());
        const result = await this.crmRequest('/api/admin/creators?' + query.toString());
        this.creators = result.data || [];
        this.creatorsTotal = result.page ? result.page.total : this.creators.length;
      } catch (error) {
        this.creators = [];
        this.creatorsTotal = 0;
        this.creatorsError = error.status === 503
          ? '达人数据库尚未连接到线上后台。'
          : (error.message || '加载达人数据失败。');
        if (error.status === 401 || error.status === 403) {
          this.clearAdminApiToken();
          this.creatorsError = '管理员访问码不正确，请重新输入。';
        }
      } finally {
        this.creatorsLoading = false;
      }
    },

    async openCreatorDetails(creatorId) {
      this.creatorsError = '';
      try {
        const result = await this.crmRequest('/api/admin/creators?creator_id=' + encodeURIComponent(creatorId));
        result.data.creator.tags = result.data.creator.tags || [];
        result.data.participations = result.data.participations || [];
        this.selectedCreator = result.data;
      } catch (error) {
        this.creatorsError = error.message || '加载 Creator 详情失败。';
      }
    },

    async toggleCreatorTag(tag) {
      if (!this.selectedCreator) return;
      const current = new Set(this.selectedCreator.creator.tags || []);
      current.has(tag) ? current.delete(tag) : current.add(tag);
      try {
        const result = await this.crmRequest(
          '/api/admin/creators?creator_id=' + encodeURIComponent(this.selectedCreator.creator.creator_id),
          { method: 'PATCH', body: JSON.stringify({ tags: Array.from(current) }) }
        );
        this.selectedCreator.creator = result.data;
        const index = this.creators.findIndex(item => item.creator_id === result.data.creator_id);
        if (index >= 0) this.creators[index] = result.data;
      } catch (error) {
        this.creatorsError = error.message || '更新 Creator 标签失败。';
      }
    },

    openWorkflowTab(tab) {
      this.activeTab = tab;
      this.restoreRememberedAdminLogin();
      this.workflowError = '';
      this.workflowJobMessage = '';
      if (!this.workflowCampaignId && this.campaigns.length > 0) {
        this.workflowCampaignId = this.campaigns[0].campaign_id;
      }
      if (!this.adminApiToken) {
        this.workflowParticipants = [];
        this.workflowError = '请先在“达人管理”中完成管理员登录。';
        return;
      }
      if (tab !== 'jobs') this.loadWorkflowParticipants();
    },

    async loadWorkflowParticipants() {
      this.restoreRememberedAdminLogin();
      this.workflowError = '';
      if (!this.adminApiToken) {
        this.workflowParticipants = [];
        this.workflowError = '请先在“达人管理”中完成管理员登录。';
        return;
      }
      if (!this.workflowCampaignId) {
        this.workflowParticipants = [];
        return;
      }
      this.workflowLoading = true;
      try {
        const query = new URLSearchParams({
          campaign_id: this.workflowCampaignId,
          limit: '200'
        });
        const result = await this.crmRequest('/api/admin/participants?' + query.toString());
        this.workflowParticipants = result.data || [];
      } catch (error) {
        this.workflowParticipants = [];
        this.workflowError = error.message || '加载 Campaign 工作流失败。';
      } finally {
        this.workflowLoading = false;
      }
    },

    async updateWorkflowStatus(participant, field, value) {
      this.workflowError = '';
      try {
        const result = await this.crmRequest(
          '/api/admin/participants?participant_id=' + encodeURIComponent(participant.participant_id),
          { method: 'PATCH', body: JSON.stringify({ [field]: value }) }
        );
        const index = this.workflowParticipants.findIndex(
          item => item.participant_id === participant.participant_id
        );
        if (index >= 0) {
          this.workflowParticipants[index] = {
            ...this.workflowParticipants[index],
            ...result.data
          };
        }
      } catch (error) {
        this.workflowError = error.message || '更新工作流状态失败。';
        await this.loadWorkflowParticipants();
      }
    },

    runWorkflowJob(jobType) {
      const labels = {
        COMMENT_IMPORT: 'Instagram 评论导入',
        PROFILE_SCREENING: 'Instagram 主页检查'
      };
      this.workflowJobMessage = `${labels[jobType] || jobType}入口已建立；待后续配置 Instagram 数据源后启用。`;
    },

    exportWorkflowCsv() {
      if (this.workflowParticipants.length === 0) {
        this.workflowError = '当前 Campaign 暂无可导出的参与记录。';
        return;
      }
      const columns = [
        ['campaign_id', 'Campaign'], ['instagram_username', 'Instagram'],
        ['product_name', '商品'], ['dm_status', 'DM状态'],
        ['shipping_status', '物流状态'], ['order_number', '订单号'],
        ['tracking_number', '物流单号'], ['carrier', '承运商'],
        ['ugc_status', 'UGC状态']
      ];
      const escapeCell = value => `"${String(value ?? '').replace(/"/g, '""')}"`;
      const rows = [columns.map(column => escapeCell(column[1])).join(',')];
      for (const participant of this.workflowParticipants) {
        rows.push(columns.map(column => escapeCell(participant[column[0]])).join(','));
      }
      const blob = new Blob(['\ufeff' + rows.join('\r\n')], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${this.workflowCampaignId}-workflow.csv`;
      link.click();
      URL.revokeObjectURL(url);
    },

    creatorTagLabel(tag) {
      return ({ favorite: 'Favorite', priority: 'Priority', do_not_invite: 'Do Not Invite' })[tag] || tag;
    },

    workflowStatusLabel(status) {
      return ({
        pending: '待处理', eligible: '符合条件', manual_review: '待人工确认', filtered: '已过滤',
        sent: '已私信', replied: '已回复', agreed: '已同意', no_response: '无回复', rejected: '已拒绝',
        submitted: '已填写', preparing: '待发货', shipped: '已发货', in_transit: '运输中', delivered: '已签收',
        waiting_for_content: '待发帖', posted: '已发帖', completed: '已完成'
      })[status] || status || '—';
    },

    formatFollowerCount(value) {
      const count = Number(value);
      if (!Number.isFinite(count)) return '—';
      if (count >= 10000) return (count / 10000).toFixed(1).replace(/\.0$/, '') + '万';
      if (count >= 1000) return (count / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
      return String(count);
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
        return date.toLocaleDateString('zh-CN', {
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
