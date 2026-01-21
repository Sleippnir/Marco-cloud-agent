# Knowledge Base

Place your personal documents here. These will be embedded into the Docker image
at build time for instant RAG queries.

## Supported Formats

- **Markdown (.md)** - Best for structured content with sections
- **Text (.txt)** - Plain text files
- **JSON (.json)** - Structured data (see format below)

## Recommended Structure

```
knowledge/
├── about_me.md          # Bio, background, interests
├── projects.md          # Project descriptions
├── skills.md            # Technical skills, tools
└── projects.json        # Structured project data (optional)
```

## Example: about_me.md

```markdown
# About Me

I'm Marco, a software engineer based in [city]. I specialize in [areas].

## Background

I started programming in [year] with [language]. Since then...

## Interests

Outside of work, I enjoy [hobbies].
```

## Example: projects.json

```json
{
  "projects": [
    {
      "name": "Project Name",
      "description": "What it does and why it matters",
      "tech": ["Python", "Pipecat", "WebRTC"],
      "role": "Lead developer",
      "highlights": "Key achievement or metric"
    }
  ]
}
```

## Building the Index

The Docker build automatically processes files in this directory:

```bash
# Local testing
python scripts/ingest_documents.py --dir knowledge/ --pattern "*.md"

# Or during Docker build (automatic)
docker build --build-arg GOOGLE_API_KEY=$GOOGLE_API_KEY -t my-avatar .
```

## Tips

- Keep chunks focused - one topic per section
- Include specifics (dates, numbers, names) for accurate retrieval
- Write in a way that sounds natural when spoken aloud
- Test queries locally before deploying
