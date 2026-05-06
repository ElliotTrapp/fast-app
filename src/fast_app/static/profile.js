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
      website: '',
      skillGroups: [],
      experience: [],
      education: [],
      certificates: [],
      awards: [],
      interests: [],
      languages: [],
      projects: [],
      preferences: { remote: false, relocationPreferences: [], employmentTypes: [], whatLookingFor: '' },
      narratives: [],
    },
    rawProfileData: {},
    newSkill: '',
    newKeywordInputs: {},
    newInterest: '',
    newRelocationPref: '',
    newEmploymentType: '',
    newProfileName: '',
    showNewProfileModal: false,
    showDeleteConfirm: false,
    showImportConfirm: false,
    pendingImportData: null,
    extractFactsOnImport: true,
    importingProfile: false,
    extractingFacts: false,
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
      this.rawProfileData = JSON.parse(JSON.stringify(d));

      const isNested = d.basics && typeof d.basics === 'object';
      const b = isNested ? d.basics : d;

      this.formData = {
        name: b.name || '',
        email: b.email || '',
        phone: b.phone || '',
        location: b.location || '',
        headline: b.headline || '',
        summary: b.summary || '',
        website: b.website || '',
        skillGroups: this._parseSkillGroups(d, isNested),
        experience: this._parseExperience(d, isNested),
        education: this._parseEducation(d, isNested),
        certificates: this._parseCertificates(d, isNested),
        awards: Array.isArray(d.awards) ? d.awards.map(a => ({...a})) : [],
        interests: Array.isArray(d.interests) ? [...d.interests] : [],
        languages: Array.isArray(d.languages) ? d.languages.map(l => ({...l})) : [],
        projects: Array.isArray(d.projects) ? d.projects.map(p => ({...p})) : [],
        preferences: this._parsePreferences(d, isNested),
        narratives: this._parseNarratives(d),
      };
    },

    _parseSkillGroups(d, isNested) {
      if (isNested && Array.isArray(d.skills)) {
        return d.skills.map(s => {
          if (typeof s === 'object' && s !== null) {
            return { name: s.name || '', keywords: Array.isArray(s.keywords) ? [...s.keywords] : [] };
          }
          return { name: 'Skills', keywords: [String(s)] };
        });
      }
      if (Array.isArray(d.skills)) {
        return [{ name: 'Skills', keywords: d.skills.map(String) }];
      }
      return [];
    },

    _parseExperience(d, isNested) {
      const source = isNested ? d.work : d.experience;
      if (!Array.isArray(source)) return [];
      return source.map(e => {
        if (isNested) {
          return {
            company: e.name || '',
            title: e.position || '',
            startDate: e.startDate || '',
            endDate: e.endDate || '',
            summary: e.summary || '',
            highlights: Array.isArray(e.highlights) ? [...e.highlights] : [],
          };
        }
        return {
          company: e.company || '',
          title: e.title || '',
          startDate: e.startDate || '',
          endDate: e.endDate || '',
          summary: e.summary || '',
          highlights: Array.isArray(e.highlights) ? [...e.highlights] : [],
        };
      });
    },

    _parseEducation(d, isNested) {
      if (!Array.isArray(d.education)) return [];
      return d.education.map(e => ({
        institution: e.institution || '',
        area: e.area || '',
        studyType: e.studyType || e.degree || '',
        startDate: e.startDate || '',
        endDate: e.endDate || '',
      }));
    },

    _parseCertificates(d, isNested) {
      let source = d.certificates;
      if (!Array.isArray(source)) source = d.certifications;
      if (!Array.isArray(source)) return [];
      return source.map(c => {
        if (typeof c === 'string') {
          return { name: c, issuer: '', date: '' };
        }
        return { name: c.name || '', issuer: c.issuer || '', date: c.date || '' };
      });
    },

    _parsePreferences(d, isNested) {
      const wp = d.workPreferences || {};
      return {
        remote: wp.remote || false,
        relocationPreferences: Array.isArray(wp.relocationPreferences) ? [...wp.relocationPreferences] : [],
        employmentTypes: Array.isArray(wp.employmentTypes) ? [...wp.employmentTypes] : [],
        whatLookingFor: wp.whatLookingFor || '',
      };
    },

    _parseNarratives(d) {
      const narratives = d.meta?.narratives;
      if (!Array.isArray(narratives)) return [];
      return narratives.map(n => ({ type: n.type || 'custom', content: n.content || '' }));
    },

    _buildProfileData() {
      return {
        basics: {
          name: this.formData.name,
          email: this.formData.email,
          phone: this.formData.phone,
          location: this.formData.location,
          headline: this.formData.headline,
          summary: this.formData.summary,
          website: this.formData.website,
        },
        work: this.formData.experience.map(e => ({
          name: e.company,
          position: e.title,
          startDate: e.startDate,
          endDate: e.endDate,
          summary: e.summary,
          highlights: e.highlights || [],
        })),
        education: this.formData.education.map(e => ({
          institution: e.institution,
          area: e.area,
          studyType: e.studyType,
          startDate: e.startDate,
          endDate: e.endDate,
        })),
        skills: this.formData.skillGroups.map(g => ({
          name: g.name,
          keywords: g.keywords,
        })),
        certificates: this.formData.certificates.map(c => ({
          name: c.name,
          issuer: c.issuer,
          date: c.date,
        })),
        awards: this.formData.awards.map(a => ({
          title: a.title,
          awarder: a.awarder,
          date: a.date,
        })),
        interests: this.formData.interests,
        languages: this.formData.languages.map(l => ({
          language: l.language,
          fluency: l.fluency,
        })),
        projects: this.formData.projects.map(p => ({
          name: p.name,
          description: p.description,
          url: p.url,
          startDate: p.startDate || '',
        })),
        workPreferences: {
          remote: this.formData.preferences.remote,
          relocationPreferences: this.formData.preferences.relocationPreferences,
          employmentTypes: this.formData.preferences.employmentTypes,
          whatLookingFor: this.formData.preferences.whatLookingFor,
        },
        meta: {
          narratives: this.formData.narratives.map(n => ({
            type: n.type,
            content: n.content,
          })),
        },
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

    saveProfileSection(sectionKey) {
      const fullData = this._buildProfileData();
      this.saveFieldDebounced('profile_data', fullData);
    },

    clearSaveStatusAfter(ms) {
      if (this.saveTimer) clearTimeout(this.saveTimer);
      this.saveTimer = setTimeout(() => {
        this.saveStatus = '';
      }, ms);
    },

    addSkillGroup() {
      this.formData.skillGroups.push({ name: '', keywords: [] });
      this.saveProfileSection('skills');
    },

    removeSkillGroup(idx) {
      this.formData.skillGroups.splice(idx, 1);
      this.saveProfileSection('skills');
    },

    addKeywordToGroup(groupIdx) {
      const input = this.newKeywordInputs[groupIdx] || '';
      const keyword = input.trim();
      if (keyword && !this.formData.skillGroups[groupIdx].keywords.includes(keyword)) {
        this.formData.skillGroups[groupIdx].keywords.push(keyword);
        this.newKeywordInputs[groupIdx] = '';
        this.saveProfileSection('skills');
      }
    },

    removeKeywordFromGroup(groupIdx, kwIdx) {
      this.formData.skillGroups[groupIdx].keywords.splice(kwIdx, 1);
      this.saveProfileSection('skills');
    },

    addExperience() {
      this.formData.experience.push({
        title: '',
        company: '',
        startDate: '',
        endDate: '',
        summary: '',
        highlights: [],
      });
    },

    removeExperience(idx) {
      this.formData.experience.splice(idx, 1);
      this.saveProfileSection('work');
    },

    addHighlight(expIdx) {
      if (!Array.isArray(this.formData.experience[expIdx].highlights)) {
        this.formData.experience[expIdx].highlights = [];
      }
      this.formData.experience[expIdx].highlights.push('');
    },

    removeHighlight(expIdx, hlIdx) {
      this.formData.experience[expIdx].highlights.splice(hlIdx, 1);
      this.saveProfileSection('work');
    },

    addEducation() {
      this.formData.education.push({
        institution: '',
        area: '',
        studyType: '',
        startDate: '',
        endDate: '',
      });
    },

    removeEducation(idx) {
      this.formData.education.splice(idx, 1);
      this.saveProfileSection('education');
    },

    addCertificate() {
      this.formData.certificates.push({ name: '', issuer: '', date: '' });
    },

    removeCertificate(idx) {
      this.formData.certificates.splice(idx, 1);
      this.saveProfileSection('certificates');
    },

    addAward() {
      this.formData.awards.push({ title: '', awarder: '', date: '' });
    },

    removeAward(idx) {
      this.formData.awards.splice(idx, 1);
      this.saveProfileSection('awards');
    },

    addInterest() {
      const val = this.newInterest.trim();
      if (val && !this.formData.interests.includes(val)) {
        this.formData.interests.push(val);
        this.newInterest = '';
        this.saveProfileSection('interests');
      }
    },

    removeInterest(idx) {
      this.formData.interests.splice(idx, 1);
      this.saveProfileSection('interests');
    },

    addLanguage() {
      this.formData.languages.push({ language: '', fluency: '' });
    },

    removeLanguage(idx) {
      this.formData.languages.splice(idx, 1);
      this.saveProfileSection('languages');
    },

    addProject() {
      this.formData.projects.push({
        name: '',
        description: '',
        url: '',
        startDate: '',
      });
    },

    removeProject(idx) {
      this.formData.projects.splice(idx, 1);
      this.saveProfileSection('projects');
    },

    addRelocationPref() {
      const val = this.newRelocationPref.trim();
      if (val && !this.formData.preferences.relocationPreferences.includes(val)) {
        this.formData.preferences.relocationPreferences.push(val);
        this.newRelocationPref = '';
        this.saveProfileSection('workPreferences');
      }
    },

    removeRelocationPref(idx) {
      this.formData.preferences.relocationPreferences.splice(idx, 1);
      this.saveProfileSection('workPreferences');
    },

    addEmploymentType() {
      const val = this.newEmploymentType.trim();
      if (val && !this.formData.preferences.employmentTypes.includes(val)) {
        this.formData.preferences.employmentTypes.push(val);
        this.newEmploymentType = '';
        this.saveProfileSection('workPreferences');
      }
    },

    removeEmploymentType(idx) {
      this.formData.preferences.employmentTypes.splice(idx, 1);
      this.saveProfileSection('workPreferences');
    },

    addNarrative() {
      this.formData.narratives.push({ type: 'summary', content: '' });
    },

    removeNarrative(idx) {
      this.formData.narratives.splice(idx, 1);
      this.saveProfileSection('narratives');
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
        this.pendingImportData = profileData;
        this.showImportConfirm = true;
      } catch (e) {
        this.error = 'Invalid JSON file';
      }
      event.target.value = '';
    },

    async confirmImport() {
      if (!this.pendingImportData) return;
      this.importingProfile = true;
      this.error = '';
      try {
        const name = this.pendingImportData.name || 'Imported Profile';
        const response = await this.$store.auth.fetchWithAuth('/api/profiles/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name,
            profile_data: this.pendingImportData,
            is_default: this.profiles.length === 0,
          }),
        });
        if (!response.ok) {
          this.error = 'Failed to import profile';
          this.importingProfile = false;
          return;
        }
        await this.loadProfiles();
        const allResp = await this.$store.auth.fetchWithAuth('/api/profiles');
        const profiles = await allResp.json();
        if (profiles.length > 0) {
          this.activeProfileId = profiles[profiles.length - 1].id;
          await this.loadActiveProfile();
        }

        if (this.extractFactsOnImport) {
          this.extractingFacts = true;
          try {
            await this.$store.auth.fetchWithAuth('/api/knowledge/facts/all', { method: 'DELETE' });
            await this.$store.auth.fetchWithAuth('/api/knowledge/extract-from-profile', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ profile_data: this.pendingImportData }),
            });
          } catch (e) {
            this.error = 'Profile imported, but fact extraction failed';
          }
        }

        this.showImportConfirm = false;
        this.pendingImportData = null;
        this.extractFactsOnImport = true;
        this.importingProfile = false;
        this.extractingFacts = false;
      } catch (e) {
        this.error = 'Network error importing profile';
        this.importingProfile = false;
        this.extractingFacts = false;
      }
    },

    cancelImport() {
      this.pendingImportData = null;
      this.showImportConfirm = false;
      this.extractFactsOnImport = true;
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