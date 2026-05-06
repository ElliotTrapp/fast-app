function jobSearchEditor() {
  return {
    query: '',
    location: '',
    datePosted: '',
    jobType: '',
    remote: false,
    jobs: [],
    total: 0,
    loading: false,
    error: '',
    expandedDescriptions: {},
    hasSearched: false,

    async searchJobs() {
      if (!this.query.trim()) return;
      this.loading = true;
      this.error = '';
      this.expandedDescriptions = {};
      try {
        const response = await this.$store.auth.fetchWithAuth('/api/jobs/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: this.query.trim(),
            location: this.location.trim(),
            num_pages: 1,
            date_posted: this.datePosted,
            job_type: this.jobType,
            remote: this.remote,
          }),
        });
        if (response.status === 503) {
          this.error = 'Job search is not configured. Set the FAST_APP_JSEARCH_API_KEY environment variable to enable job search.';
          return;
        }
        if (!response.ok) {
          this.error = 'Failed to search for jobs. Please try again.';
          return;
        }
        const data = await response.json();
        this.jobs = data.jobs;
        this.total = data.total;
        this.hasSearched = true;
      } catch (e) {
        this.error = 'Network error searching for jobs';
      } finally {
        this.loading = false;
      }
    },

    toggleDescription(jobId) {
      this.expandedDescriptions[jobId] = !this.expandedDescriptions[jobId];
    },

    isDescriptionExpanded(jobId) {
      return !!this.expandedDescriptions[jobId];
    },

    generateResume(job) {
      const url = job.job_url || job.apply_link || '';
      if (url) {
        window.location.href = '/?url=' + encodeURIComponent(url);
      }
    },

    formatSalary(job) {
      if (!job.salary_min && !job.salary_max) return '';
      const currency = job.salary_currency === 'USD' ? '$' : (job.salary_currency || '');
      if (job.salary_min && job.salary_max) {
        return `${currency}${job.salary_min.toLocaleString()} - ${currency}${job.salary_max.toLocaleString()}${job.salary_period ? '/' + job.salary_period : ''}`;
      }
      if (job.salary_min) {
        return `From ${currency}${job.salary_min.toLocaleString()}${job.salary_period ? '/' + job.salary_period : ''}`;
      }
      return `Up to ${currency}${job.salary_max.toLocaleString()}${job.salary_period ? '/' + job.salary_period : ''}`;
    },
  };
}