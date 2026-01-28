# v0 Website Integration Guide

This document describes how to integrate the Marco Voice Avatar with a v0-deployed personal website, where clicking your headshot launches your AI clone for a voice conversation.

## Overview

The Simli avatar is a **video clone of you** — same face, lip-synced to the AI's speech. When visitors click your static headshot, it "comes alive" as an interactive version of you.

**User Experience Flow:**
1. Visitor sees your headshot on the website
2. Visitor clicks the headshot
3. Headshot is replaced by your Simli video clone (same face, now animated)
4. Voice conversation begins — your clone speaks with your voice (Cartesia) and your knowledge (RAG)
5. Clicking again (or saying "goodbye") ends the session and restores the static headshot

**Technical Flow:**
```
[Click Headshot]
       ↓
[v0 Frontend] → POST /api/start-session → [Your API Route]
       ↓                                          ↓
       ↓                           [Pipecat Cloud API: start agent]
       ↓                                          ↓
       ↓                           ← { roomUrl, token } ←
       ↓
[daily-js connects to Daily room]
       ↓
[Pipecat agent joins same room]
       ↓
[Video: Simli avatar replaces headshot]
[Audio: Two-way conversation begins]
```

## Prerequisites

- Pipecat Cloud account with `marco-voice-avatar` agent deployed
- Daily.co account (Pipecat Cloud uses Daily for WebRTC)
- v0/Vercel project for the frontend
- API keys stored in Vercel environment variables
- **Simli face clone** of yourself (see below)
- **Cartesia voice clone** of yourself (optional, for full likeness)

## Creating Your Clone

### Simli Face Clone

1. Go to [Simli.com](https://simli.com) and create an account
2. Upload a short video of yourself (10-30 seconds, good lighting, face visible)
3. Simli generates a `face_id` — this is your `SIMLI_FACE_ID`
4. The avatar will lip-sync to any audio, matching your facial expressions

**Tips for best results:**
- Neutral background, even lighting
- Look directly at camera
- Include some natural head movement and expressions
- Higher resolution = better clone quality

### Cartesia Voice Clone (Optional)

For the AI to speak in *your* voice:

1. Go to [Cartesia.ai](https://cartesia.ai) and create an account
2. Record voice samples (a few minutes of clear speech)
3. Clone your voice and get a `voice_id` — this is your `CARTESIA_VOICE_ID`

Without a voice clone, the avatar uses a standard Cartesia voice. Still works great, just won't sound exactly like you.

### Update Your Secrets

After creating your clones, update the Pipecat Cloud secret set:

```bash
pipecat cloud secrets set marco \
  SIMLI_FACE_ID=your_new_face_id \
  CARTESIA_VOICE_ID=your_new_voice_id
```

## Architecture

### Components

| Component | Role | Location |
|-----------|------|----------|
| v0 Frontend | UI, Daily client, video display | Vercel Edge |
| API Route | Starts Pipecat sessions, returns room credentials | Vercel Serverless |
| Pipecat Cloud | Runs the voice agent | Pipecat infrastructure |
| Daily | WebRTC transport (audio/video) | Daily infrastructure |
| Simli | Avatar video generation | Simli infrastructure |

### Data Flow

1. **Session Start**: Frontend → API Route → Pipecat Cloud → Daily room created
2. **WebRTC Connect**: Frontend joins Daily room, agent joins same room
3. **Media Streams**: 
   - User audio → Daily → Agent (Deepgram STT → OpenAI → Cartesia TTS)
   - Agent video (Simli) → Daily → Frontend video element
4. **Session End**: User says "goodbye" or clicks to end → Agent calls `end_call` → Room closes

## Frontend Implementation

### 1. Install Dependencies

```bash
npm install @daily-co/daily-js
# or for React:
npm install @daily-co/daily-react
```

### 2. Environment Variables (Vercel)

Add these to your Vercel project settings:

```env
# Pipecat Cloud credentials (required)
PIPECAT_CLOUD_API_KEY=pcc_xxxxxxxxxxxxxxxxxxxx
PIPECAT_AGENT_NAME=marco-voice-avatar
```

**Get your API key:**
```bash
# From CLI
pipecat cloud api-key create website-integration

# Or from dashboard: https://pipecat.daily.co → API Keys
```

### 3. API Route: Start Session

Create `app/api/start-session/route.ts` (Next.js App Router):

```typescript
import { NextResponse } from 'next/server';

const PIPECAT_CLOUD_API = 'https://api.pipecat.daily.co';

export async function POST() {
  try {
    // Start a new Pipecat Cloud session
    // Endpoint: POST /v1/public/{agent_name}/start
    const response = await fetch(
      `${PIPECAT_CLOUD_API}/v1/public/${process.env.PIPECAT_AGENT_NAME}/start`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.PIPECAT_CLOUD_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          // Request Daily room (Pipecat Cloud creates it)
          createDailyRoom: true,
          // Optional: pass custom data to your bot
          // body: { userId: "...", customField: "..." },
          // Optional: customize Daily room properties
          // dailyRoomProperties: { enable_chat: false },
        }),
      }
    );

    if (!response.ok) {
      const error = await response.text();
      console.error('Pipecat Cloud error:', error);
      return NextResponse.json({ error: 'Failed to start session' }, { status: 500 });
    }

    const data = await response.json();
    
    // Return room credentials to frontend
    return NextResponse.json({
      roomUrl: data.room_url,
      token: data.token,
      sessionId: data.session_id,
    });
  } catch (error) {
    console.error('Session start error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
```

### 4. Frontend Component: Avatar Trigger

Create a React component that handles the headshot → avatar transition:

```tsx
'use client';

import { useState, useRef, useCallback } from 'react';
import Daily, { DailyCall } from '@daily-co/daily-js';

interface AvatarProps {
  headshotSrc: string;
  headshotAlt?: string;
  className?: string;
}

export function InteractiveAvatar({ headshotSrc, headshotAlt = 'Profile photo', className }: AvatarProps) {
  const [isActive, setIsActive] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const videoRef = useRef<HTMLVideoElement>(null);
  const callRef = useRef<DailyCall | null>(null);

  const startSession = useCallback(async () => {
    if (isConnecting || isActive) return;
    
    setIsConnecting(true);
    setError(null);

    try {
      // 1. Request session from API
      const response = await fetch('/api/start-session', { method: 'POST' });
      if (!response.ok) throw new Error('Failed to start session');
      
      const { roomUrl, token } = await response.json();

      // 2. Create Daily call object
      const call = Daily.createCallObject({
        videoSource: false, // We don't send video, only receive
      });
      callRef.current = call;

      // 3. Handle incoming video track (the Simli avatar)
      call.on('track-started', (event) => {
        if (event.track.kind === 'video' && event.participant && !event.participant.local) {
          // Attach avatar video to our video element
          if (videoRef.current) {
            videoRef.current.srcObject = new MediaStream([event.track]);
          }
        }
      });

      // 4. Handle session end
      call.on('left-meeting', () => {
        endSession();
      });

      call.on('participant-left', (event) => {
        // If the bot leaves, end the session
        if (event.participant && !event.participant.local) {
          endSession();
        }
      });

      // 5. Join the Daily room
      await call.join({ url: roomUrl, token });
      
      // 6. Enable microphone for voice input
      await call.setLocalAudio(true);
      
      setIsActive(true);
    } catch (err) {
      console.error('Session error:', err);
      setError(err instanceof Error ? err.message : 'Connection failed');
      endSession();
    } finally {
      setIsConnecting(false);
    }
  }, [isConnecting, isActive]);

  const endSession = useCallback(() => {
    if (callRef.current) {
      callRef.current.leave();
      callRef.current.destroy();
      callRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsActive(false);
    setIsConnecting(false);
  }, []);

  return (
    <div className={`relative cursor-pointer ${className}`} onClick={isActive ? endSession : startSession}>
      {/* Headshot (visible when inactive) */}
      {!isActive && (
        <div className="relative">
          <img
            src={headshotSrc}
            alt={headshotAlt}
            className={`w-full h-full object-cover transition-opacity ${isConnecting ? 'opacity-50' : ''}`}
          />
          {isConnecting && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/20">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-white border-t-transparent" />
            </div>
          )}
          {!isConnecting && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/20 transition-colors">
              <span className="text-white opacity-0 hover:opacity-100 transition-opacity text-sm font-medium">
                Click to chat
              </span>
            </div>
          )}
        </div>
      )}

      {/* Avatar video (visible when active) */}
      {isActive && (
        <div className="relative">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            className="w-full h-full object-cover"
          />
          <div className="absolute bottom-2 right-2 bg-red-500 text-white text-xs px-2 py-1 rounded-full animate-pulse">
            Live
          </div>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="absolute bottom-2 left-2 right-2 bg-red-500/90 text-white text-xs p-2 rounded">
          {error}
        </div>
      )}
    </div>
  );
}
```

### 5. Usage in Your Page

```tsx
import { InteractiveAvatar } from '@/components/InteractiveAvatar';

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center">
      <h1 className="text-4xl font-bold mb-8">Welcome</h1>
      
      {/* Replace your static headshot with the interactive component */}
      <InteractiveAvatar
        headshotSrc="/images/headshot.jpg"
        headshotAlt="Marco's photo"
        className="w-64 h-64 rounded-full overflow-hidden shadow-lg"
      />
      
      <p className="mt-4 text-gray-600">Click to start a conversation</p>
    </main>
  );
}
```

## Pipecat Cloud API Reference

**Verified from `pipecatcloud` SDK v0.2.18**

### API Base URL

```
https://api.pipecat.daily.co
```

### Start Session (Public Endpoint)

This is the endpoint your v0 frontend API route will call:

```
POST https://api.pipecat.daily.co/v1/public/{agent_name}/start
Authorization: Bearer {PIPECAT_CLOUD_API_KEY}
Content-Type: application/json
```

**Request Body:**
```json
{
  "createDailyRoom": true,
  "body": {},
  "dailyRoomProperties": {
    "enable_chat": false,
    "enable_screenshare": false
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `createDailyRoom` | Yes | Set to `true` to have Pipecat Cloud create a Daily room |
| `body` | No | Custom data passed to your bot's `SessionArguments` |
| `dailyRoomProperties` | No | Daily room configuration (only when `createDailyRoom: true`) |

**Response (Success):**
```json
{
  "room_url": "https://your-org.daily.co/abc123xyz",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "session_id": "sess_abc123"
}
```

### Get API Key

Get your public API key from the Pipecat Cloud dashboard or CLI:

```bash
# View current auth
pipecat cloud auth show

# Or create a new API key
pipecat cloud api-key create my-website-key
```

### List Active Sessions

```
GET https://api.pipecat.daily.co/v1/organizations/{org}/services/{agent_name}/sessions
Authorization: Bearer {PIPECAT_CLOUD_API_KEY}
```

### Terminate Session

```
DELETE https://api.pipecat.daily.co/v1/organizations/{org}/services/{agent_name}/sessions/{session_id}
Authorization: Bearer {PIPECAT_CLOUD_API_KEY}
```

> **Note**: Sessions automatically terminate when the user says "goodbye" (triggers `end_call` function) or when all participants leave the Daily room.

## Security Considerations

### API Key Protection

- **Never expose** `PIPECAT_CLOUD_API_KEY` in frontend code
- Use Vercel environment variables (not `.env.local` committed to git)
- The API route runs server-side, keeping the key secure

### Rate Limiting

Add rate limiting to prevent abuse:

```typescript
// app/api/start-session/route.ts
import { Ratelimit } from '@upstash/ratelimit';
import { Redis } from '@upstash/redis';

const ratelimit = new Ratelimit({
  redis: Redis.fromEnv(),
  limiter: Ratelimit.slidingWindow(5, '1 m'), // 5 sessions per minute per IP
});

export async function POST(request: Request) {
  const ip = request.headers.get('x-forwarded-for') ?? 'anonymous';
  const { success } = await ratelimit.limit(ip);
  
  if (!success) {
    return NextResponse.json({ error: 'Rate limited' }, { status: 429 });
  }
  
  // ... rest of handler
}
```

### CORS

Vercel handles CORS for same-origin requests automatically. If you need cross-origin:

```typescript
// app/api/start-session/route.ts
export async function OPTIONS() {
  return new NextResponse(null, {
    headers: {
      'Access-Control-Allow-Origin': 'https://your-domain.com',
      'Access-Control-Allow-Methods': 'POST',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
}
```

## Styling Tips

### Matching Your Headshot to Simli Output

For a seamless "photo comes alive" effect:

1. **Use the same framing**: Simli outputs a head-and-shoulders shot. Match your static headshot to this framing.
2. **Similar lighting**: If your Simli training video had warm lighting, use a headshot with similar tones.
3. **Same aspect ratio**: Simli outputs 512×512 (square). Use a square headshot.

### Smooth Transition

```css
.avatar-container {
  position: relative;
  width: 256px;
  height: 256px;
  border-radius: 50%;
  overflow: hidden;
}

.avatar-container img,
.avatar-container video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: opacity 0.3s ease;
}
```

### Matching Video Dimensions

The Simli avatar outputs 512×512 video. Ensure your container maintains aspect ratio:

```css
.avatar-container {
  aspect-ratio: 1;
  max-width: 512px;
}
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| No video appears | Track not attached | Check `track-started` event handler |
| Audio not working | Microphone permission denied | Request permission before joining |
| "Failed to start session" | API key invalid or agent not deployed | Verify env vars and agent status |
| Video freezes | Network issues | Daily handles reconnection automatically |
| Avatar doesn't speak | STT not receiving audio | Check `setLocalAudio(true)` is called |

### Debug Mode

Add logging to diagnose issues:

```typescript
call.on('error', (e) => console.error('Daily error:', e));
call.on('participant-updated', (e) => console.log('Participant:', e));
call.on('track-started', (e) => console.log('Track:', e.track.kind, e.participant?.user_name));
```

## Testing Locally

1. Run your v0 app locally: `npm run dev`
2. Ensure Pipecat Cloud agent is deployed and running
3. Click the headshot to test the full flow
4. Check browser console for errors
5. Check Pipecat Cloud logs: `pipecat cloud agent logs marco-voice-avatar`

## Cost Considerations

| Service | Billing Model | Estimate |
|---------|---------------|----------|
| Pipecat Cloud | Per-minute agent runtime | ~$0.01-0.05/min |
| Daily | Free tier: 2,000 participant-minutes/month | Free for personal site |
| Deepgram | Per-minute audio | ~$0.01/min |
| OpenAI | Per-token | ~$0.001-0.01/response |
| Cartesia | Per-character | ~$0.001/response |
| Simli | Per-minute video | Varies by plan |

For a personal website with light traffic, expect < $10/month.

## Next Steps

1. Deploy the agent to Pipecat Cloud (see `SESSION_HANDOFF.md`)
2. Add the API route to your v0 project
3. Integrate the `InteractiveAvatar` component
4. Configure environment variables in Vercel
5. Test end-to-end
6. Add analytics to track usage

## References

- [Pipecat Cloud Docs](https://docs.pipecat.ai/deployment/pipecat-cloud/)
- [Daily.co JavaScript SDK](https://docs.daily.co/reference/daily-js)
- [Daily React Hooks](https://docs.daily.co/reference/daily-react)
- [Vercel Environment Variables](https://vercel.com/docs/environment-variables)
- [v0 by Vercel](https://v0.dev/)
