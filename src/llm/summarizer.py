from src.llm.provider import LLMProvider
from src.core.logging import get_logger
from typing import List, Dict, Any
import json

logger = get_logger(__name__)

class ResultSummarizer:
    """Generate natural language summaries of SQL results"""
    
    def __init__(self, session_id: str = "summarizer"):
        self.llm_provider = LLMProvider(session_id=session_id)
    
    async def summarize(
        self,
        user_query: str,
        sql: str,
        columns: List[str],
        rows: List[tuple],
        total_rows: int
    ) -> str:
        """Generate a human-readable summary of query results"""
        
        if not rows:
            return "No results found for your query."
        
        # Prepare data for LLM
        sample_data = []
        for row in rows[:10]:  # First 10 rows only
            sample_data.append(dict(zip(columns, row)))
        
        # Calculate basic stats if numeric columns exist
        stats = self._calculate_stats(columns, rows)
        
        prompt = f"""Analyze these query results and provide a clear, concise business summary.

Original Question: {user_query}

SQL Query: {sql}

Results Summary:
- Total rows returned: {total_rows}
- Columns: {', '.join(columns)}

Sample Data (first 10 rows):
{json.dumps(sample_data, indent=2, default=str)}

{stats}

Provide a 2-3 sentence natural language summary that:
1. Answers the user's question directly
2. Highlights key insights from the data
3. Uses business-friendly language (no technical jargon)

Summary:"""
        
        try:
            summary = await self.llm_provider.generate_response(prompt)
            return summary.strip()
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return f"Query returned {total_rows} rows with columns: {', '.join(columns)}"
    
    def _calculate_stats(self, columns: List[str], rows: List[tuple]) -> str:
        """Calculate basic statistics for numeric columns"""
        if not rows:
            return ""
        
        stats_text = "\nBasic Statistics:\n"
        
        for i, col in enumerate(columns):
            try:
                values = [row[i] for row in rows if row[i] is not None]
                if values and isinstance(values[0], (int, float)):
                    stats_text += f"  - {col}: min={min(values)}, max={max(values)}, avg={sum(values)/len(values):.2f}\n"
            except:
                continue
        
        return stats_text if stats_text != "\nBasic Statistics:\n" else ""
