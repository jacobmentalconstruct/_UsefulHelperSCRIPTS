import time
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceCompoundRoutingMS',
    version='1.0.0',
    description='Pilfered from chunkers/compound.py routing/remap logic. Resolves sub-chunker routing and remaps section spans into compound coordinates.',
    tags=['compound', 'chunking', 'routing'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceCompoundRoutingMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={}, outputs={'registry': 'dict'}, description='Build default logical sub-chunker registry map by source type and optional language.', tags=['compound', 'registry'])
    def build_default_registry(self) -> Dict[str, str]:
        # Key encoding: "source_type|language" where language="*" is wildcard.
        registry = {
            'code|*': 'ProseChunker',
            'prose|*': 'ProseChunker',
            'structured|*': 'ProseChunker',
            'generic|*': 'ProseChunker',
        }
        for lang in ['python', 'javascript', 'typescript', 'java', 'go', 'rust', 'cpp', 'c', 'c_sharp', 'ruby', 'php', 'swift', 'kotlin', 'scala', 'bash']:
            registry[f'code|{lang}'] = 'TreeSitterProxy'
        for lang in ['json', 'yaml', 'toml', 'html', 'css', 'xml']:
            registry[f'structured|{lang}'] = 'TreeSitterProxy'
        return registry

    @service_endpoint(inputs={'source_type': 'str', 'language': 'str'}, outputs={'engine': 'str'}, description='Resolve logical sub-chunker using exact (type+language) then wildcard fallback.', tags=['compound', 'routing'])
    def resolve_sub_chunker(self, source_type: str, language: str = '') -> str:
        reg = self.build_default_registry()
        exact = f'{source_type}|{language}'
        if exact in reg:
            return reg[exact]
        wildcard = f'{source_type}|*'
        if wildcard in reg:
            return reg[wildcard]
        return 'ProseChunker'

    @service_endpoint(inputs={'sub_chunks': 'list', 'offset': 'int', 'max_line': 'int', 'compound_name': 'str', 'section_name': 'str', 'source_cid': 'str'}, outputs={'chunks': 'list'}, description='Remap sub-chunk spans into compound-document coordinates with clamping.', tags=['compound', 'remap'])
    def remap_chunks(self, sub_chunks: List[Dict[str, Any]], offset: int, max_line: int, compound_name: str, section_name: str, source_cid: str) -> List[Dict[str, Any]]:
        remapped: List[Dict[str, Any]] = []
        for chunk in sub_chunks:
            spans = chunk.get('spans', [])
            new_spans = []
            for span in spans:
                start = max(0, min(int(span.get('line_start', 0)) + offset, max_line))
                end = max(0, min(int(span.get('line_end', 0)) + offset, max_line))
                if start > end:
                    start, end = end, start
                new_spans.append({'source_cid': source_cid, 'line_start': start, 'line_end': end})
            if not new_spans:
                continue

            sub_path = list(chunk.get('heading_path', []))
            if sub_path and sub_path[0] == section_name:
                sub_path = sub_path[1:]

            remapped.append({
                'chunk_type': chunk.get('chunk_type', 'section'),
                'name': chunk.get('name', section_name),
                'spans': new_spans,
                'heading_path': [compound_name, section_name] + sub_path,
                'depth': int(chunk.get('depth', 0)) + 1,
                'semantic_depth': int(chunk.get('semantic_depth', 0)),
                'structural_depth': int(chunk.get('structural_depth', 0)),
                'language_tier': chunk.get('language_tier', 'unknown'),
            })
        return remapped

    @service_endpoint(inputs={'compound_name': 'str', 'section': 'dict', 'source_cid': 'str'}, outputs={'chunk': 'dict'}, description='Create virtual-file marker chunk for a detected section boundary.', tags=['compound', 'marker'])
    def make_virtual_file_chunk(self, compound_name: str, section: Dict[str, Any], source_cid: str) -> Dict[str, Any]:
        content_preview_end = min(int(section.get('content_start', 0)) + 5, int(section.get('line_end', 0)))
        return {
            'chunk_type': 'virtual_file',
            'name': section.get('name', 'virtual_file'),
            'spans': [{'source_cid': source_cid, 'line_start': int(section.get('line_start', 0)), 'line_end': content_preview_end}],
            'heading_path': [compound_name, section.get('name', 'virtual_file')],
            'depth': 0,
            'language_tier': section.get('language_tier', 'unknown'),
        }

    @service_endpoint(inputs={'compound_name': 'str', 'sections': 'list', 'line_count': 'int', 'source_cid': 'str'}, outputs={'chunk': 'dict'}, description='Create compound-summary chunk preview for detected sections.', tags=['compound', 'summary'])
    def make_compound_summary(self, compound_name: str, sections: List[Dict[str, Any]], line_count: int, source_cid: str) -> Dict[str, Any]:
        end = min(40, max(0, line_count - 1))
        label = f"{compound_name} ({len(sections)} files)"
        return {
            'chunk_type': 'compound_summary',
            'name': label,
            'spans': [{'source_cid': source_cid, 'line_start': 0, 'line_end': end}],
            'heading_path': [compound_name, '(summary)'],
            'depth': 0,
            'language_tier': 'unknown',
        }

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}
