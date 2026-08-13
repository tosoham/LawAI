"""
Unit tests for RAG Service
"""
from unittest.mock import Mock, patch

import pytest

from services.rag_service import RAGService, get_rag_service


class TestRAGService:
    """Test cases for RAG Service"""

    @pytest.fixture
    def mock_vector_service(self):
        """Mock vector service"""
        mock = Mock()
        mock.search.return_value = {
            'documents': [
                'Section 479 - Bail in non-bailable offences...',
                'Section 482 - Anticipatory bail...'
            ],
            'metadatas': [
                {
                    'section_number': '479',
                    'title': 'Bail in non-bailable offences',
                    'act': 'Bharatiya Nagarik Suraksha Sanhita',
                    'year': '2023'
                },
                {
                    'section_number': '482',
                    'title': 'Anticipatory bail',
                    'act': 'Bharatiya Nagarik Suraksha Sanhita',
                    'year': '2023'
                }
            ],
            'distances': [0.1, 0.2],
            'ids': ['bnss_479', 'bnss_482']
        }
        return mock

    @pytest.fixture
    def mock_llm_service(self):
        """Mock LLM service"""
        mock = Mock()
        mock.generate.return_value = "Based on the legal provisions, anticipatory bail can be granted under Section 482 of BNSS..."
        return mock

    @pytest.fixture
    def rag_service(self, mock_vector_service, mock_llm_service):
        """Create RAG service with mocked dependencies"""
        with patch('services.rag_service.get_vector_service', return_value=mock_vector_service):
            with patch('services.rag_service.llm_service', mock_llm_service):
                service = RAGService()
                return service

    def test_format_context(self, rag_service):
        """Test context formatting"""
        search_results = {
            'documents': ['Section 479 text...'],
            'metadatas': [{
                'section_number': '479',
                'title': 'Bail provisions',
                'act': 'BNSS',
                'year': '2023'
            }]
        }

        context = rag_service._format_context(search_results)

        assert 'Section 479' in context
        assert 'BNSS' in context
        assert 'Bail provisions' in context

    def test_format_context_empty(self, rag_service):
        """Test context formatting with empty results"""
        search_results = {'documents': [], 'metadatas': []}

        context = rag_service._format_context(search_results)

        assert 'No relevant legal provisions found' in context

    def test_format_sources(self, rag_service):
        """Test source formatting"""
        search_results = {
            'documents': ['Section 479 text...'],
            'metadatas': [{'section_number': '479', 'act': 'BNSS'}],
            'distances': [0.1],
            'ids': ['bnss_479']
        }

        sources = rag_service._format_sources(search_results)

        assert len(sources) == 1
        assert sources[0]['id'] == 'bnss_479'
        assert 'relevance_score' in sources[0]
        assert sources[0]['relevance_score'] > 0.8  # 1 - 0.1 = 0.9

    def test_create_prompt(self, rag_service):
        """Test prompt creation"""
        query = "What are bail provisions?"
        context = "Section 479 - Bail in non-bailable offences..."

        prompt = rag_service._create_prompt(query, context)

        assert query in prompt
        assert context in prompt
        assert 'legal ai assistant' in prompt.lower()
        assert 'disclaimer' in prompt.lower()

    def test_search_and_generate_success(self, rag_service, mock_vector_service, mock_llm_service):
        """Test successful RAG search and generation"""
        result = rag_service.search_and_generate(
            query="What are bail provisions?",
            collection="bnss_sections",
            top_k=5
        )

        assert 'answer' in result
        assert 'sources' in result
        assert 'query' in result
        assert result['query'] == "What are bail provisions?"
        assert len(result['sources']) > 0
        assert 'DISCLAIMER' in result['answer']

        # Verify services were called
        mock_vector_service.search.assert_called_once()
        mock_llm_service.generate.assert_called_once()

    def test_search_and_generate_no_results(self, rag_service, mock_vector_service):
        """Test RAG search with no results"""
        mock_vector_service.search.return_value = {
            'documents': [],
            'metadatas': [],
            'distances': [],
            'ids': []
        }

        result = rag_service.search_and_generate(
            query="Unknown query",
            collection="bnss_sections",
            top_k=5
        )

        assert 'answer' in result
        assert "couldn't find relevant" in result['answer'].lower()
        assert len(result['sources']) == 0

    def test_multi_collection_search(self, rag_service, mock_vector_service, mock_llm_service):
        """Test multi-collection search"""
        result = rag_service.multi_collection_search(
            query="What are bail provisions?",
            collections=["bnss_sections", "bns_sections"],
            top_k_per_collection=3
        )

        assert 'answer' in result
        assert 'sources' in result
        assert 'collections' in result
        assert len(result['collections']) == 2

        # Verify vector service was called for each collection
        assert mock_vector_service.search.call_count == 2

    def test_multi_collection_search_no_results(self, rag_service, mock_vector_service):
        """Test multi-collection search with no results"""
        mock_vector_service.search.return_value = {
            'documents': [],
            'metadatas': [],
            'distances': [],
            'ids': []
        }

        result = rag_service.multi_collection_search(
            query="Unknown query",
            collections=["bnss_sections"],
            top_k_per_collection=3
        )

        assert 'answer' in result
        assert "couldn't find relevant" in result['answer'].lower()

    def test_get_rag_service_singleton(self):
        """Test that get_rag_service returns singleton"""
        with patch('services.rag_service.get_vector_service'):
            with patch('services.rag_service.llm_service'):
                service1 = get_rag_service()
                service2 = get_rag_service()

                assert service1 is service2


class TestRAGServiceIntegration:
    """Integration tests for RAG Service (require actual services)"""

    @pytest.mark.integration
    def test_format_context_with_judgement(self):
        """Test context formatting with court judgement"""
        service = RAGService()

        search_results = {
            'documents': ['Arnesh Kumar vs State of Bihar...'],
            'metadatas': [{
                'case_name': 'Arnesh Kumar vs State of Bihar',
                'citation': '(2014) 8 SCC 273',
                'year': '2014',
                'court': 'Supreme Court of India'
            }]
        }

        context = service._format_context(search_results)

        assert 'Arnesh Kumar' in context
        assert '(2014) 8 SCC 273' in context

    @pytest.mark.integration
    def test_format_sources_relevance_score(self):
        """Test relevance score calculation"""
        service = RAGService()

        search_results = {
            'documents': ['Doc 1', 'Doc 2'],
            'metadatas': [{'id': '1'}, {'id': '2'}],
            'distances': [0.0, 0.5],  # 0.0 = perfect match, 0.5 = moderate match
            'ids': ['id1', 'id2']
        }

        sources = service._format_sources(search_results)

        assert sources[0]['relevance_score'] == 1.0  # 1 - 0.0
        assert sources[1]['relevance_score'] == 0.5  # 1 - 0.5


class TestGraphContext:
    """
    Graph material is rendered with its kinds kept apart, and the separation is
    load-bearing rather than cosmetic. Related sections and judgements are
    pointers -- the graph holds their titles and one-line subjects, not their
    text -- so the prompt must let the model cite them without licensing it to
    say what they provide. Flattening the two is how a pointer becomes a
    fabricated holding.
    """

    @pytest.fixture
    def service(self):
        return RAGService.__new__(RAGService)

    @pytest.fixture
    def graph(self):
        from services.legal_graph import get_legal_graph

        return get_legal_graph()

    def test_seeds_come_from_the_top_hits_only(self, service):
        results = {
            "metadatas": [
                {"short_name": "BNSS", "section_number": str(n)} for n in range(1, 8)
            ]
        }
        context = service._expand_over_graph(results)
        assert len(context.seeds) <= 3

    def test_a_judgement_collection_hit_yields_no_seeds(self, service):
        """Judgement chunks carry no section number; expansion is a no-op."""
        results = {"metadatas": [{"case_name": "Bachan Singh v. State of Punjab"}]}
        assert service._expand_over_graph(results).is_empty

    def test_empty_results_do_not_reach_the_graph(self, service):
        assert service._expand_over_graph({}).is_empty

    def test_pointers_carry_their_restriction_into_the_prompt(self, service, graph):
        rendered = service._format_graph_context(graph.expand(["BNSS 482"]))
        cases = rendered.split("JUDGEMENTS RECORDED")[1]
        assert "must NOT state what it held" in cases
        sections = rendered.split("CROSS-REFERENCED PROVISIONS")[1]
        assert "must NOT state what they provide" in sections

    def test_facts_are_marked_as_statable(self, service, graph):
        rendered = service._format_graph_context(graph.expand(["BNS 103"]))
        assert "may be stated" in rendered.split("OFFENCE CLASSIFICATION")[1]
        assert "Non-bailable" in rendered

    def test_a_contested_provision_instructs_both_sides(self, service, graph):
        rendered = service._format_graph_context(graph.expand(["BNSS 480"]))
        assert "CONTESTED" in rendered
        assert "do not present one of them as the answer" in rendered

    def test_nothing_connected_renders_nothing(self, service, graph):
        assert service._format_graph_context(graph.expand([])) == ""

    def test_the_prompt_omits_the_section_entirely_when_empty(self, service):
        prompt = service._create_prompt("what is murder", "context here", "")
        assert "CONNECTED MATERIAL" not in prompt

    def test_the_prompt_carries_connected_material_when_present(self, service):
        prompt = service._create_prompt("q", "context", "DOCTRINE: something")
        assert "CONNECTED MATERIAL" in prompt
        assert "DOCTRINE: something" in prompt
