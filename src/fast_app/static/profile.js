function profileEditor() {
  return {
    profiles: [],
    activeProfileId: null,
    activeProfile: null,
    formData: {
      name: '',
      email: '',
      phone: '',
      location: '',
      headline: '',
      summary: '',
      skills: [],
      experience: [],
      education: [],
      certifications: [],
      projects: [],
    },
    newSkill: '',
    newCertification: '',
    newProfileName: '',
    showNewProfileModal: false,
    showDeleteConfirm: false,
    loading: true,
    error: '',
    saveStatus: '',
    saveTimer: null,
    debounceTimers: {},

    async init() {
      await this.loadProfiles();
    },

    async loadProfiles() {
      this.loading = true;
      this.error = '';
      try {
        const response = await this.$store.auth.fetchWithAuth('/api/profiles');
        if (!response.ok) {
          this.error = 'Failed to load profiles';
          return;
        }
        this.profiles = await response.json();
        if (this.profiles.length > 0) {
          const defaultProfile = this.profiles.find(p => p.is_default);
          this.activeProfileId = (defaultProfile || this.profiles[0]).id;
          await this.loadActiveProfile();
        }
      } catch (e) {
        this.error = 'Network error loading profiles';
      } finally {
        this.loading = false;
      }
    },

    async loadActiveProfile() {
      if (!this.activeProfileId) return;
      this.error = '';
      try {
        const response = await this.$store.auth.fetchWithAuth(`/api/profiles/${this.activeProfileId}`);
        if (!response.ok) {
          this.error = 'Failed to load profile';
          return;
        }
        this.activeProfile = await response.json();
        this.populateFormData();
      } catch (e) {
        this.error = 'Network error loading profile';
      }
    },

    populateFormData() {
      if (!this.activeProfile) return;
      const d = this.activeProfile.profile_data || {};
      this.formData = {
        name: d.name || '',
        email: d.email || '',
        phone: d.phone || '',
        location: d.location || '',
        headline: d.headline || '',
        summary: d.summary || '',
        skills: Array.isArray(d.skills) ? [...d.skills] : [],
        experience: Array.isArray(d.experience) ? d.experience.map(e => ({...e})) : [],
        education: Array.isArray(d.education) ? d.education.map(e => ({...e})) : [],
        certifications: Array.isArray(d.certifications) ? [...d.certifications] : [],
        projects: Array.isArray(d.projects) ? d.projects.map(p => ({...p})) : [],
      };
    },

    async switchProfile() {
      await this.loadActiveProfile();
    },

    async addProfile() {
      this.newProfileName = '';
      this.showNewProfileModal = true;
    },

    async confirmNewProfile() {
      if (!this.newProfileName.trim()) return;
      this.error = '';
      try {
        const response = await this.$store.auth.fetchWithAuth('/api/profiles', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: this.newProfileName.trim(),
            profile_data: {},
            is_default: this.profiles.length === 0,
          }),
        });
        if (!response.ok) {
          this.error = 'Failed to create profile';
          return;
        }
        this.showNewProfileModal = false;
        await this.loadProfiles();
        const newProfile = await this.$store.auth.fetchWithAuth('/api/profiles');
        const profiles = await newProfile.json();
        if (profiles.length > 0) {
          this.activeProfileId = profiles[profiles.length - 1].id;
          await this.loadActiveProfile();
        }
      } catch (e) {
        this.error = 'Network error creating profile';
      }
    },

    async deleteProfile() {
      if (!this.activeProfileId) return;
      this.error = '';
      try {
        const response = await this.$store.auth.fetchWithAuth(`/api/profiles/${this.activeProfileId}`, {
          method: 'DELETE',
        });
        if (!response.ok && response.status !== 204) {
          this.error = 'Failed to delete profile';
          return;
        }
        this.showDeleteConfirm = false;
        this.activeProfileId = null;
        this.activeProfile = null;
        await this.loadProfiles();
      } catch (e) {
        this.error = 'Network error deleting profile';
      }
    },

    async toggleDefault() {
      if (!this.activeProfile) return;
      const newDefault = !this.activeProfile.is_default;
      await this.saveField('is_default', newDefault);
      this.activeProfile.is_default = newDefault;
      this.profiles.forEach(p => p.is_default = (p.id === this.activeProfileId) ? newDefault : false);
    },

    async saveField(field, value) {
      if (!this.activeProfileId) return;
      this.saveStatus = 'saving';
      this.error = '';
      try {
        const body = {};
        body[field] = value;
        const response = await this.$store.auth.fetchWithAuth(`/api/profiles/${this.activeProfileId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!response.ok) {
          this.saveStatus = 'error';
          return;
        }
        this.activeProfile = await response.json();
        this.saveStatus = 'saved';
        this.clearSaveStatusAfter(3000);
      } catch (e) {
        this.saveStatus = 'error';
      }
    },

    saveFieldDebounced(field, value) {
      const key = field;
      if (this.debounceTimers[key]) {
        clearTimeout(this.debounceTimers[key]);
      }
      this.debounceTimers[key] = setTimeout(() => {
        this.saveField(field, value);
        delete this.debounceTimers[key];
      }, 500);
    },

    clearSaveStatusAfter(ms) {
      if (this.saveTimer) clearTimeout(this.saveTimer);
      this.saveTimer = setTimeout(() => {
        this.saveStatus = '';
      }, ms);
    },

    addSkill() {
      const skill = this.newSkill.trim();
      if (skill && !this.formData.skills.includes(skill)) {
        this.formData.skills.push(skill);
        this.newSkill = '';
        this.saveField('profile_data', { skills: this.formData.skills });
      }
    },

    removeSkill(idx) {
      this.formData.skills.splice(idx, 1);
      this.saveField('profile_data', { skills: this.formData.skills });
    },

    addExperience() {
      this.formData.experience.push({
        title: '',
        company: '',
        startDate: '',
        endDate: '',
        summary: '',
      });
    },

    removeExperience(idx) {
      this.formData.experience.splice(idx, 1);
      this.saveField('profile_data', { experience: this.formData.experience });
    },

    addEducation() {
      this.formData.education.push({
        institution: '',
        degree: '',
        startDate: '',
        endDate: '',
      });
    },

    removeEducation(idx) {
      this.formData.education.splice(idx, 1);
      this.saveField('profile_data', { education: this.formData.education });
    },

    addCertification() {
      const cert = this.newCertification.trim();
      if (cert && !this.formData.certifications.includes(cert)) {
        this.formData.certifications.push(cert);
        this.newCertification = '';
        this.saveField('profile_data', { certifications: this.formData.certifications });
      }
    },

    removeCertification(idx) {
      this.formData.certifications.splice(idx, 1);
      this.saveField('profile_data', { certifications: this.formData.certifications });
    },

    addProject() {
      this.formData.projects.push({
        name: '',
        description: '',
        url: '',
      });
    },

    removeProject(idx) {
      this.formData.projects.splice(idx, 1);
      this.saveField('profile_data', { projects: this.formData.projects });
    },

    async importProfile() {
      document.getElementById('import-file-input').click();
    },

    async handleImportFile(event) {
      const file = event.target.files[0];
      if (!file) return;
      this.error = '';
      try {
        const text = await file.text();
        const profileData = JSON.parse(text);
        const name = profileData.name || file.name.replace('.json', '');
        const response = await this.$store.auth.fetchWithAuth('/api/profiles/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name,
            profile_data: profileData,
            is_default: this.profiles.length === 0,
          }),
        });
        if (!response.ok) {
          this.error = 'Failed to import profile';
          return;
        }
        await this.loadProfiles();
        const allResp = await this.$store.auth.fetchWithAuth('/api/profiles');
        const profiles = await allResp.json();
        if (profiles.length > 0) {
          this.activeProfileId = profiles[profiles.length - 1].id;
          await this.loadActiveProfile();
        }
      } catch (e) {
        this.error = 'Invalid JSON file';
      }
      event.target.value = '';
    },

    async exportProfile() {
      if (!this.activeProfileId) return;
      this.error = '';
      try {
        const response = await this.$store.auth.fetchWithAuth(`/api/profiles/${this.activeProfileId}/export`);
        if (!response.ok) {
          this.error = 'Failed to export profile';
          return;
        }
        const data = await response.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(this.activeProfile?.name || 'profile').replace(/\s+/g, '_')}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } catch (e) {
        this.error = 'Network error exporting profile';
      }
    },
  };
}