# Fast-App

Generate tailored resumes from job URLs using AI and import them to Reactive Resume.

## Features

- Extract job data from URLs using Ollama
- Generate tailored resumes and cover letters with AI
- Interactive Q&A to customize resume content
- Automatic upload to Reactive Resume
- Web interface for easy use

## Installation

```bash
pip install -e .
```

## Usage

### CLI

```bash
fast-app generate <job-url>
```

### Web Interface

```bash
fast-app serve
```

Then open http://localhost:8000 in your browser.

## Configuration

Create a `config.json` file with your settings:

```json
{
  "ollama": {
    "endpoint": "http://localhost:11434",
    "model": "llama3.2"
  },
  "resume": {
    "endpoint": "http://localhost:3000",
    "api_key": "your-api-key"
  }
}
```

## License

MIT