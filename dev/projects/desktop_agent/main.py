import os
import sys
import asyncio
import argparse
from dotenv import load_dotenv



from projects.desktop_agent.organizer import FileOrganizer
from lane_queue.store import CommandStore
from lane_queue.models import RiskLevel
from llm_router import LLMRouter

load_dotenv()

async def run_organizer(directory: str):
    """
    Main loop for the file organizer.
    """
    organizer = FileOrganizer()
    store = CommandStore()
    
    # Start the LLM Router for categorization
    router = LLMRouter.get_instance()
    router.start()
    
    try:
        print(f"[*] Desktop Agent starting. Scanning: {directory}")
        
        # 1. Create a lane for this session
        session_id = f"desktop-agent-{os.getlogin()}"
        lane = store.create_lane(
            session_id=session_id,
            name="File Organization",
            risk_level=RiskLevel.HIGH # Moves require review
        )
        print(f"[+] Created session lane: {lane.id}")
        
        # 2. Scan
        files = organizer.scan(directory)
        print(f"[*] Found {len(files)} files to consider.")
        
        # 3. Categorize & Propose
        for file_path in files:
            print(f"[*] Processing: {os.path.basename(file_path)}...")
            category_obj = await organizer.categorize(file_path)
            
            if category_obj.confidence > 0.5:
                print(f"  [>] Proposing move to: {category_obj.category} (Reason: {category_obj.reasoning})")
                cmd_id = organizer.propose_move(file_path, category_obj.category, lane_id=lane.id)
                print(f"  [+] Enqueued command: {cmd_id}")
            else:
                print(f"  [!] Skipping: low confidence ({category_obj.confidence})")
                
        print("[*] Scan complete. Check the Queue for pending move operations.")
        
    finally:
        router.stop()

def main():
    parser = argparse.ArgumentParser(description="Agent OS — Desktop Agent (File System Automation)")
    parser.add_argument("--dir", default=os.getenv("WATCH_DIRECTORIES", "."), help="Directory to scan")
    args = parser.parse_args()
    
    # Handle the string representation of list if coming from .env
    target_dir = args.dir
    if target_dir.startswith("[") and target_dir.endswith("]"):
        import json
        try:
            target_dir = json.loads(target_dir.replace("'", '"'))[0]
        except:
            pass
            
    if not os.path.isdir(target_dir):
        print(f"Error: {target_dir} is not a valid directory.")
        sys.exit(1)
        
    asyncio.run(run_organizer(target_dir))

if __name__ == "__main__":
    main()
