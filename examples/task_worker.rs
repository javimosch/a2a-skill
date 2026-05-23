use serde_json::{json, from_str};
use std::time::SystemTime;

// Assuming a2a crate is imported
// In a real setup: use a2a::Client;
// For this example, we'll use the relative path

#[path = "../src/lib.rs"]
mod a2a;

use a2a::Client;

#[derive(serde::Deserialize, Debug)]
struct Task {
    id: String,
    work: String,
    #[serde(default)]
    priority: String,
}

fn main() {
    let client = match Client::new("production", "worker-1") {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Client creation failed: {}", e);
            return;
        }
    };

    // Register as active
    if let Err(e) = client.set_status("active") {
        eprintln!("Failed to set status: {}", e);
    }

    println!("Worker-1 started, waiting for tasks...");

    loop {
        // Wait for task (30 second timeout)
        match client.recv(30, true, false, Some(1)) {
            Ok(messages) => {
                if messages.is_empty() {
                    println!("No tasks received, exiting");
                    break;
                }

                // Process first message
                let msg = &messages[0];

                // Try to parse as JSON task
                match from_str::<Task>(&msg.body) {
                    Ok(task) => {
                        println!("Task received: {} (priority: {})", task.id, task.priority);
                        println!("Work: {}", task.work);

                        // Simulate work
                        std::thread::sleep(std::time::Duration::from_secs(1));

                        // Report completion
                        let result = json!({
                            "task_id": task.id,
                            "status": "complete",
                            "result": format!("Completed: {}", task.work),
                            "completed_at": SystemTime::now()
                                .duration_since(SystemTime::UNIX_EPOCH)
                                .unwrap()
                                .as_secs_f64()
                        });

                        if let Err(e) = client.send("coordinator", &result.to_string(), None, None) {
                            eprintln!("Failed to send result: {}", e);
                        } else {
                            println!("Result sent for task {}", task.id);
                        }
                    }
                    Err(_) => {
                        // Not a task JSON, skip
                        println!("Skipping non-task message");
                    }
                }
            }
            Err(e) => {
                eprintln!("Error receiving messages: {}", e);
                break;
            }
        }
    }

    // Mark as done
    if let Err(e) = client.set_status("done") {
        eprintln!("Failed to set final status: {}", e);
    }

    println!("Worker-1 shutdown complete");
}
