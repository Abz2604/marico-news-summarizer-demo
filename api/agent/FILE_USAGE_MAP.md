# 📁 Agent Folder File Usage Map

**Generated**: 2024-11-07  
**Purpose**: Categorize which files are actively used vs legacy/unused

---

## ✅ **ACTIVELY USED FILES - CORE SYSTEM**

### **Main Orchestration**
| File | Purpose | Used By | Status |
|------|---------|---------|--------|
| `graph.py` | Main agent orchestration & workflow | Entry point | 🟢 ACTIVE |
| `smart_navigator.py` | Recursive LLM-driven navigation | `graph.py` | 🟢 ACTIVE |
| `types.py` | Data models (ArticleContent, SeedLink, etc.) | All modules | 🟢 ACTIVE |

### **Phase 2: Strategic Capabilities (NEW)**
| File | Purpose | Used By | Status |
|------|---------|---------|--------|
| `planner.py` | Strategic planning before navigation | `graph.py` | 🟢 ACTIVE (Phase 2) |
| `reflector.py` | Self-evaluation & metacognition | `graph.py` | 🟢 ACTIVE (Phase 2) |
| `focus_agent.py` | Token optimization pre-filtering | `content_extractor_llm.py` | 🟢 ACTIVE (Phase 2) |

### **Intent & Decision Making**
| File | Purpose | Used By | Status |
|------|---------|---------|--------|
| `intent_extractor.py` | Extract user intent from prompts | `graph.py` | 🟢 ACTIVE |
| `intent.py` | Intent data models (UserIntent, TimeRange, etc.) | `intent_extractor.py` | 🟢 ACTIVE |
| `page_decision.py` | LLM-based page analysis & action decision | `smart_navigator.py` | 🟢 ACTIVE |

### **Content Processing**
| File | Purpose | Used By | Status |
|------|---------|---------|--------|
| `content_extractor_llm.py` | LLM-based content extraction | `smart_navigator.py` | 🟢 ACTIVE |
| `link_extractor_smart.py` | LLM-based link extraction | `smart_navigator.py` | 🟢 ACTIVE |
| `deduplicator.py` | Remove duplicate articles | `graph.py` | 🟢 ACTIVE |

### **Infrastructure**
| File | Purpose | Used By | Status |
|------|---------|---------|--------|
| `brightdata_fetcher.py` | Web scraping via Bright Data | `graph.py`, `smart_navigator.py` | 🟢 ACTIVE |
| `utils.py` | Text extraction utilities | `graph.py` | 🟢 ACTIVE |
| `__init__.py` | Package initialization | Python import system | 🟢 ACTIVE |

---

## 🟡 **LEGACY FILES - IMPORTED BUT NOT USED**

These files are imported in `graph.py` but **never actually called** in the current workflow:

| File | Original Purpose | Why Unused | Recommendation |
|------|------------------|------------|----------------|
| `link_extractor.py` | Old rule-based link extraction | Replaced by `link_extractor_smart.py` | 🔴 Can remove import |
| `page_analyzer.py` | Old rule-based page analysis | Replaced by `page_decision.py` | 🔴 Can remove import |
| `context_extractor.py` | Rule-based context extraction | Replaced by `context_extractor_llm.py` | 🔴 Can remove import |
| `context_extractor_llm.py` | LLM context extraction | Not used in Phase 2 smart navigation | 🔴 Can remove import |
| `date_parser.py` | Standalone date extraction | Integrated into content extraction | 🔴 Can remove import |
| `content_validator.py` | Content quality validation | Integrated into relevance validation | 🔴 Can remove import |

**Note**: These files still exist and may work, but they're **not part of the active execution flow**.

---

## 🔵 **STANDALONE/UTILITY FILES**

| File | Purpose | Status |
|------|---------|--------|
| `navigator.py` | Old navigation logic (pre-Phase 1) | ⚪ DEPRECATED - Not imported anywhere |

---

## 📦 **ADAPTERS SUBFOLDER**

| File | Purpose | Status |
|------|---------|--------|
| `adapters/base.py` | Base adapter interface | ⚪ UNUSED - Not part of current flow |
| `adapters/default.py` | Default adapter implementation | ⚪ UNUSED - Not part of current flow |
| `adapters/registry.py` | Adapter registry pattern | ⚪ UNUSED - Not part of current flow |

**Status**: Adapters subfolder appears to be an **architectural experiment** that was never integrated.

---

## 🎯 **EXECUTION FLOW MAP**

```
User Request
    ↓
graph.py (run_agent)
    ├─→ intent_extractor.py (extract_intent) ✅
    │   └─→ intent.py (UserIntent model) ✅
    │
    ├─→ planner.py (create_navigation_plan) ✅ Phase 2
    │
    ├─→ smart_navigator.py (run_smart_navigation) ✅
    │   ├─→ brightdata_fetcher.py (fetch_url) ✅
    │   ├─→ page_decision.py (analyze_and_decide) ✅
    │   ├─→ link_extractor_smart.py (extract_relevant_links) ✅
    │   └─→ content_extractor_llm.py (extract_content, validate_relevance) ✅
    │       └─→ focus_agent.py (extract_focused_content) ✅ Phase 2
    │
    ├─→ deduplicator.py (deduplicate_articles) ✅
    │
    ├─→ reflector.py (reflect_on_results) ✅ Phase 2
    │
    └─→ Summarization (built-in to graph.py) ✅
```

---

## 📊 **STATISTICS**

| Category | Count | Percentage |
|----------|-------|------------|
| **Active Core Files** | 14 files | 60% |
| **Legacy/Unused Imports** | 6 files | 26% |
| **Deprecated** | 1 file | 4% |
| **Unused Adapters** | 3 files | 13% |

**Total Files**: 23  
**Actually Used**: 14 (61%)  
**Can Be Cleaned**: 9 (39%)

---

## 🧹 **CLEANUP RECOMMENDATIONS**

### **Safe to Remove (Imports Only)**
These are imported but never called - safe to remove from `graph.py`:

```python
# IN graph.py - REMOVE THESE IMPORTS:
from .link_extractor import extract_article_links_with_ai  # ❌
from .page_analyzer import analyze_page_for_content  # ❌
from .context_extractor import extract_context_from_url_and_prompt, validate_page_relevance  # ❌
from .context_extractor_llm import extract_context_with_llm  # ❌
from .date_parser import extract_article_date  # ❌
from .content_validator import validate_content  # ❌
```

### **Consider Removing (Files)**
If you want to clean up the codebase:

1. **Low Priority** (keep for reference):
   - `link_extractor.py` (superseded by smart version)
   - `page_analyzer.py` (superseded by page_decision)
   - `context_extractor.py` (superseded by LLM version)

2. **Medium Priority**:
   - `context_extractor_llm.py` (not used in Phase 2)
   - `date_parser.py` (integrated into content extraction)
   - `content_validator.py` (integrated into relevance check)

3. **High Priority** (truly unused):
   - `navigator.py` (deprecated, pre-Phase 1)
   - `adapters/` folder (architectural experiment never used)

---

## ✨ **PHASE 2 ADDITIONS**

New files added in Phase 2 improvements:

1. ✅ `planner.py` - Strategic planning
2. ✅ `reflector.py` - Self-evaluation  
3. ✅ `focus_agent.py` - Token optimization

All three are **fully integrated** and **actively used**.

---

## 🎯 **SUMMARY**

**Current State**: Your agent has a **clean core** (14 active files) with some **legacy baggage** (6 unused imports, 3 deprecated files).

**Recommendation**: 
- **Immediate**: Remove unused imports from `graph.py` (5 lines)
- **Optional**: Archive legacy files to `/legacy` folder for reference
- **Keep**: All 14 actively used files - they're the production system

**System Health**: 🟢 **HEALTHY** - Core is clean, legacy doesn't interfere with execution

