import json
import codecs
import logging
from typing import AsyncGenerator, Dict, Any, Optional

logger = logging.getLogger(__name__)

class HardenedStreamingJsonParser:
    """
    🛡️ Hardened Byte-Safe Incremental JSON Parser
    Extracts the conversational "response" field in real-time from an OpenAI JSON stream
    without waiting for the full JSON block to complete.
    """
    def __init__(self, max_buffer_size: int = 128 * 1024):
        self.max_buffer_size = max_buffer_size
        self.utf8_decoder = codecs.getincrementaldecoder("utf-8")()
        
        # State Machine Variables
        self.state = "seeking_key"  # seeking_key, collecting_key, seeking_value, collecting_text, skipping_value, finished
        self.escaped = False
        self.depth = 0
        self.key_buffer = ""
        self.text_buffer = []
        self.full_content_accumulator = []
        
        # Active token state
        self.current_key = None
        self.inside_string = False
        self.parser_recovery_triggered = False

    def feed_chunk(self, chunk_bytes: bytes) -> AsyncGenerator[str, None]:
        """
        Feeds a chunk of bytes into the parser, yielding text tokens when available.
        """
        try:
            chars = self.utf8_decoder.decode(chunk_bytes, final=False)
        except Exception as e:
            logger.error(f"❌ Unicode decode error in stream chunk: {e}")
            return
            
        for char in chars:
            self.full_content_accumulator.append(char)
            
            # Enforce max memory safety boundaries
            if len(self.full_content_accumulator) > self.max_buffer_size:
                raise ValueError("Payload exceeds safety threshold limit.")
                
            # Track bracket nesting depth for JSON structure safety
            if not self.inside_string:
                if char == '{':
                    self.depth += 1
                    continue
                elif char == '}':
                    self.depth -= 1
                    continue
            
            # State Machine: Seek and Extract Text
            if self.state == "seeking_key":
                if char == '"':
                    self.inside_string = True
                    self.key_buffer = ""
                    self.state = "collecting_key"
                    
            elif self.state == "collecting_key":
                if char == '"' and not self.escaped:
                    self.inside_string = False
                    self.current_key = self.key_buffer
                    self.state = "seeking_value"
                else:
                    if char == '\\' and not self.escaped:
                        self.escaped = True
                    else:
                        self.key_buffer += char
                        self.escaped = False
                        
            elif self.state == "seeking_value":
                if char == '"':
                    self.inside_string = True
                    self.state = "collecting_text" if self.current_key == "response" else "skipping_value"
                    
            elif self.state == "collecting_text":
                # Escape logic to safely skip \" or \\ or pass them along
                if char == '\\' and not self.escaped:
                    self.escaped = True
                    continue
                    
                if char == '"' and not self.escaped:
                    # Closing quote of the response field!
                    self.inside_string = False
                    self.state = "seeking_key"
                    self.current_key = None
                else:
                    # Yield single byte-safe character token
                    yield char
                    self.text_buffer.append(char)
                    self.escaped = False
                    
            elif self.state == "skipping_value":
                if char == '"' and not self.escaped:
                    self.inside_string = False
                    self.state = "seeking_key"
                    self.current_key = None
                else:
                    if char == '\\' and not self.escaped:
                        self.escaped = True
                    else:
                        self.escaped = False

    def finalize_and_get_full_object(self) -> Dict[str, Any]:
        """
        Parses the complete accumulated payload once the stream is sealed.
        """
        # Close out utf8 decoder
        try:
            self.utf8_decoder.decode(b"", final=True)
        except Exception:
            pass
            
        full_str = "".join(self.full_content_accumulator).strip()
        
        # Incomplete recovery fallbacks
        if not full_str.endswith("}"):
            # Append closing brackets to recover incomplete JSON structures dynamically
            bracket_gap = self.depth
            if bracket_gap > 0:
                full_str += "}" * bracket_gap
                self.parser_recovery_triggered = True
                
        try:
            return json.loads(full_str)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse full accumulated JSON payload: {e}. Raw: {full_str}")
            self.parser_recovery_triggered = True
            # Try a raw text extraction fallback to prevent complete failure
            text_collected = "".join(self.text_buffer)
            return {
                "response": text_collected or "⚠️ De response kon niet volledig worden geladen.",
                "action": None, "draft": None, "state": None, "reasoning": None
            }

import asyncio
from backend.utils.openai_client import stream_gpt_json

async def stream_gpt_json_response(prompt: str, system_role: str) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Calls OpenAI stream inside a worker thread, feeds chunks into HardenedStreamingJsonParser,
    and yields parsed text tokens in real-time, followed by the finalized envelope dict.
    """
    parser = HardenedStreamingJsonParser()
    
    # Run the blocking stream request in a separate thread
    def run_stream():
        try:
            return stream_gpt_json(prompt=prompt, system_role=system_role)
        except Exception as e:
            logger.error(f"❌ OpenAI stream call error: {e}")
            raise e

    stream = await asyncio.to_thread(run_stream)
    
    # Iterate over stream chunks safely
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            # Feed the content into parser
            content_bytes = delta.content.encode("utf-8")
            for token in parser.feed_chunk(content_bytes):
                yield {"event": "text", "data": token}
                
        # Give control back to the async loop
        await asyncio.sleep(0.001)

    # Stream is complete, finalize the accumulated JSON envelope
    full_obj = parser.finalize_and_get_full_object()
    full_obj["parser_recovery_triggered"] = parser.parser_recovery_triggered
    yield {"event": "envelope", "data": full_obj}
