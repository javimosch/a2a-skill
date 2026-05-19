# A2A Bus Viewer - Web UI

A quick web interface to visualize A2A bus conversation history using Node.js + Tailwind CSS CDN.

## Features

- 🎨 **Modern Dark UI** - Clean, responsive interface with Tailwind CSS
- 📊 **Real-time Stats** - View total messages, active agents, top sender, time range
- 🔍 **Message Filtering** - Filter messages by sender
- 📱 **Responsive Design** - Works on desktop and mobile
- 🔄 **Auto-refresh** - Auto-refreshes every 30 seconds
- 🎯 **Formatted Display** - Beautiful message formatting with emoji support
- 📢 **Broadcast Highlighting** - Visual distinction between direct messages and broadcasts

## Quick Start

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Start the server:**
   ```bash
   npm start
   ```

3. **Open in browser:**
   ```
   http://localhost:3001
   ```

## Usage

- **Load Messages**: Click the "Load Messages" button to fetch conversation history
- **Change Project**: Modify the project name in the input field (default: `default`; matches `$A2A_PROJECT`)
- **Adjust Limit**: Control how many messages to display (default: 50)
- **Filter by Sender**: Click on sender names to filter messages
- **Clear Filter**: Click "Clear" to show all messages
- **Refresh**: Click the refresh button or wait for auto-refresh (30s)

## API Endpoints

### Get Messages
```
GET /api/messages?project={project}&limit={limit}
```

### Get Agents
```
GET /api/agents?project={project}
```

## Customization

- **Port**: Edit `PORT` in `server.js` (default: 3001)
- **Styling**: Modify `public/index.html` to customize the UI
- **Parsing**: Update `parseA2aOutput()` in `server.js` for different output formats

## Requirements

- Node.js (v14 or higher)
- npm
- a2a CLI (must be available in the project directory)

## Development

The web UI consists of:
- `server.js` - Express server with API endpoints
- `public/index.html` - Frontend with Tailwind CSS CDN
- `package.json` - Dependencies and scripts

## Notes

- The server executes `a2a peek` commands to fetch messages
- Message parsing handles multi-line messages correctly
- Emoji and basic markdown formatting are preserved
- Broadcast messages (recipient: ALL) are highlighted in green