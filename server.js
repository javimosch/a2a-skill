const express = require('express');
const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3001;

// Middleware
app.use(express.json());
app.use(express.static('public'));

// API endpoint to get a2a message history
app.get('/api/messages', async (req, res) => {
  try {
    const project = req.query.project || 'default';
    const limit = req.query.limit || 100;
    
    // Execute a2a peek command
    exec(`./a2a --project ${project} peek --limit ${limit}`, (error, stdout, stderr) => {
      if (error) {
        console.error('Error executing a2a peek:', error);
        return res.status(500).json({ error: 'Failed to fetch messages' });
      }
      
      // Parse the output
      const messages = parseA2aOutput(stdout);
      res.json(messages);
    });
  } catch (error) {
    console.error('Error:', error);
    res.status(500).json({ error: 'Server error' });
  }
});

// API endpoint to get agent list
app.get('/api/agents', async (req, res) => {
  try {
    const project = req.query.project || 'default';
    
    exec(`./a2a --project ${project} list --json`, (error, stdout, stderr) => {
      if (error) {
        console.error('Error executing a2a list:', error);
        return res.status(500).json({ error: 'Failed to fetch agents' });
      }
      
      try {
        const agents = JSON.parse(stdout);
        res.json(agents);
      } catch (parseError) {
        console.error('Error parsing JSON:', parseError);
        res.status(500).json({ error: 'Failed to parse agent data' });
      }
    });
  } catch (error) {
    console.error('Error:', error);
    res.status(500).json({ error: 'Server error' });
  }
});

// Parse a2a peek output into structured data
function parseA2aOutput(output) {
  const messages = [];
  const lines = output.split('\n');
  
  let currentMessage = null;
  
  for (const line of lines) {
    if (!line.trim()) continue;
    
    // Parse format: [timestamp] #id sender -> recipient
    const match = line.match(/^\[(\d{2}:\d{2}:\d{2})\]\s+#(\d+)\s+(\S+)\s+->\s+(\S+)\s*(.*)$/);
    if (match) {
      // Save previous message if exists
      if (currentMessage) {
        messages.push(currentMessage);
      }
      
      const [, timestamp, id, sender, recipient, body] = match;
      currentMessage = {
        id: parseInt(id),
        timestamp,
        sender,
        recipient,
        body: body.trim()
      };
    } else if (currentMessage) {
      // Append line to current message body
      currentMessage.body += '\n' + line.trim();
    }
  }
  
  // Don't forget the last message
  if (currentMessage) {
    messages.push(currentMessage);
  }
  
  return messages;
}

// Serve the main HTML file
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`🚀 A2A Bus Viewer running at http://localhost:${PORT}`);
  console.log(`📡 Pass ?project=NAME to the API endpoints to view a specific project (default: 'default')`);
});