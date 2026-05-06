function knowledgeEditor() {
  return {
    facts: [],
    categories: [],
    selectedCategory: 'all',
    searchQuery: '',
    editingFact: null,
    newFact: { content: '', category: 'general' },
    showAddForm: false,
    loading: false,
    error: '',
    selectedFactIds: [],
    selectAll: false,
    showBulkDeleteConfirm: false,

    async init() {
      await Promise.all([this.loadFacts(), this.loadCategories()]);
    },

    async loadFacts() {
      this.loading = true;
      this.error = '';
      this.selectedFactIds = [];
      this.selectAll = false;
      try {
        let url = '/api/knowledge/facts';
        const params = new URLSearchParams();
        if (this.selectedCategory && this.selectedCategory !== 'all') {
          params.set('category', this.selectedCategory);
        }
        if (this.searchQuery.trim()) {
          const searchResponse = await this.$store.auth.fetchWithAuth(
            '/api/knowledge/search?' + new URLSearchParams({ query: this.searchQuery, n: '50' }).toString()
          );
          if (!searchResponse.ok) {
            this.error = 'Failed to search facts';
            return;
          }
          this.facts = await searchResponse.json();
          return;
        }
        if (params.toString()) {
          url += '?' + params.toString();
        }
        const response = await this.$store.auth.fetchWithAuth(url);
        if (!response.ok) {
          this.error = 'Failed to load facts';
          return;
        }
        this.facts = await response.json();
      } catch (e) {
        this.error = 'Network error loading facts';
      } finally {
        this.loading = false;
      }
    },

    async loadCategories() {
      try {
        const response = await this.$store.auth.fetchWithAuth('/api/knowledge/categories');
        if (response.ok) {
          this.categories = await response.json();
        }
      } catch (e) {
        // Categories are optional, don't show error
      }
    },

    async addFact() {
      if (!this.newFact.content.trim()) return;
      this.error = '';
      try {
        const response = await this.$store.auth.fetchWithAuth('/api/knowledge/facts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content: this.newFact.content.trim(),
            category: this.newFact.category,
          }),
        });
        if (response.status === 409) {
          this.error = 'A fact with this content already exists';
          return;
        }
        if (!response.ok) {
          this.error = 'Failed to add fact';
          return;
        }
        this.newFact = { content: '', category: 'general' };
        this.showAddForm = false;
        await Promise.all([this.loadFacts(), this.loadCategories()]);
      } catch (e) {
        this.error = 'Network error adding fact';
      }
    },

    async deleteFact(id) {
      this.error = '';
      try {
        const response = await this.$store.auth.fetchWithAuth('/api/knowledge/facts', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: [id] }),
        });
        if (!response.ok && response.status !== 200) {
          this.error = 'Failed to delete fact';
          return;
        }
        await Promise.all([this.loadFacts(), this.loadCategories()]);
      } catch (e) {
        this.error = 'Network error deleting fact';
      }
    },

    startEdit(fact) {
      this.editingFact = { ...fact };
    },

    async saveEdit() {
      if (!this.editingFact) return;
      this.error = '';
      try {
        const body = {};
        if (this.editingFact.content) body.content = this.editingFact.content;
        if (this.editingFact.category) body.category = this.editingFact.category;

        const response = await this.$store.auth.fetchWithAuth(
          `/api/knowledge/facts/${this.editingFact.id}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          }
        );
        if (!response.ok) {
          this.error = 'Failed to update fact';
          return;
        }
        this.editingFact = null;
        await Promise.all([this.loadFacts(), this.loadCategories()]);
      } catch (e) {
        this.error = 'Network error updating fact';
      }
    },

    cancelEdit() {
      this.editingFact = null;
    },

    toggleSelectAll() {
      if (this.selectAll) {
        this.selectedFactIds = [];
        this.selectAll = false;
      } else {
        this.selectedFactIds = this.facts.map(f => f.id);
        this.selectAll = true;
      }
    },

    toggleSelectFact(id) {
      const idx = this.selectedFactIds.indexOf(id);
      if (idx >= 0) {
        this.selectedFactIds.splice(idx, 1);
      } else {
        this.selectedFactIds.push(id);
      }
      this.selectAll = this.facts.length > 0 && this.selectedFactIds.length === this.facts.length;
    },

    isSelected(id) {
      return this.selectedFactIds.includes(id);
    },

    selectedCount() {
      return this.selectedFactIds.length;
    },

    confirmBulkDelete() {
      this.showBulkDeleteConfirm = true;
    },

    cancelBulkDelete() {
      this.showBulkDeleteConfirm = false;
    },

    async deleteSelected() {
      if (this.selectedFactIds.length === 0) return;
      this.error = '';
      try {
        const response = await this.$store.auth.fetchWithAuth('/api/knowledge/facts', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: this.selectedFactIds }),
        });
        if (!response.ok && response.status !== 200) {
          this.error = 'Failed to delete selected facts';
          return;
        }
        this.selectedFactIds = [];
        this.selectAll = false;
        this.showBulkDeleteConfirm = false;
        await Promise.all([this.loadFacts(), this.loadCategories()]);
      } catch (e) {
        this.error = 'Network error deleting facts';
      }
    },
  };
}