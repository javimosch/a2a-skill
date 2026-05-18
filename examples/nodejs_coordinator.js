#!/usr/bin/env node
/**
 * Example: Node.js Task Coordinator Agent
 *
 * Demonstrates:
 * - Broadcasting work assignments
 * - Aggregating responses from multiple agents
 * - Status tracking
 * - Graceful completion
 */

const A2AClient = require('../a2a_client');
const agentId = 'nodejs-coordinator';

async function main() {
  const client = new A2AClient(process.env.A2A_PROJECT || 'default', agentId);

  console.log(`[${agentId}] Starting coordinator`);

  // Get peer list
  const peers = await client.listPeers();
  const workers = peers
    .filter(p => p.id !== agentId && p.status === 'active')
    .map(p => p.id);

  console.log(`[${agentId}] Found ${workers.length} active workers`);

  // Broadcast task assignment
  const taskData = {
    tasks: [
      'Validate data quality',
      'Run performance tests',
      'Update documentation'
    ],
    deadline: new Date(Date.now() + 5 * 60000).toISOString()
  };

  await client.send('all', JSON.stringify({
    type: 'task_assignment',
    data: taskData
  }));

  console.log(`[${agentId}] Assigned tasks to ${workers.length} workers`);

  // Wait for responses
  const timeout = 30;
  const gotResponses = await client.waitForMessages(workers.length, timeout);

  if (!gotResponses) {
    console.log(`[${agentId}] Timeout waiting for responses`);
  }

  // Collect all responses
  const responses = await client.recv();
  const completions = [];

  for (const msg of responses) {
    try {
      const data = JSON.parse(msg.body);
      if (data.type === 'task_completion') {
        completions.push({
          worker: msg.sender,
          tasks: data.tasks_completed,
          duration: data.duration_seconds
        });
        console.log(`[${agentId}] ${msg.sender} completed ${data.tasks_completed} tasks in ${data.duration_seconds}s`);
      }
    } catch (e) {
      // Skip non-JSON messages
    }
  }

  // Generate summary
  const totalTasks = completions.reduce((sum, c) => sum + c.tasks, 0);
  const summary = {
    type: 'sprint_summary',
    workers_responded: completions.length,
    total_tasks_completed: totalTasks,
    completion_time: new Date().toISOString(),
    details: completions
  };

  await client.send('all', JSON.stringify(summary));
  console.log(`[${agentId}] Summary: ${completions.length} workers completed ${totalTasks} tasks`);

  // Get final stats
  const stats = await client.stats();
  console.log(`[${agentId}] Bus stats: ${stats.messages} messages, ${stats.agents_done} agents done`);

  // Mark done
  await client.setStatus('done');
  console.log(`[${agentId}] Marked as done`);
}

main().catch(err => {
  console.error(`[${agentId}] Error:`, err.message);
  process.exit(1);
});
