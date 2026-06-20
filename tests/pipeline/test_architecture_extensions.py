"""测试新的架构扩展功能

对应思维实验#1 和 思维实验#2 要求的特性：
1. 信息不足三模式 (Query/Assume/Ask)
2. 状态作为语义类型
3. 调试循环结构化
4. AskUser 节点

这些测试验证新添加的语义类型和路由器是否正常工作。
"""

import pytest

from omnicompany.protocol.format import Format, create_builtin_registry


class TestInfoInsufficiencyTypes:
    """测试信息不足处理相关的语义类型"""
    
    def test_info_insufficient_type_exists(self):
        """测试 info.insufficient 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("info.insufficient")
        assert fmt is not None
        assert fmt.id == "info.insufficient"
        assert fmt.name == "InsufficientInformation"
        assert "signal.info_gap" in fmt.tags
    
    def test_kb_query_result_type_exists(self):
        """测试 kb.query.result 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("kb.query.result")
        assert fmt is not None
        assert fmt.id == "kb.query.result"
        assert fmt.name == "KBQueryResult"
        assert "action.query" in fmt.tags
    
    def test_assumption_proposal_type_exists(self):
        """测试 assumption.proposal 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("assumption.proposal")
        assert fmt is not None
        assert fmt.id == "assumption.proposal"
        assert fmt.name == "AssumptionProposal"
        assert "requires.verification" in fmt.tags
    
    def test_user_answer_type_exists(self):
        """测试 user.answer 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("user.answer")
        assert fmt is not None
        assert fmt.id == "user.answer"
        assert fmt.name == "UserAnswer"
        assert "action.ask" in fmt.tags
    
    def test_info_insufficient_is_requirement_subclass(self):
        """测试 info.insufficient 是 requirement 的子类型"""
        registry = create_builtin_registry()
        fmt = registry.get("info.insufficient")
        assert fmt.parent == "requirement"


class TestStateTypes:
    """测试状态相关的语义类型"""
    
    def test_git_committed_state_exists(self):
        """测试 state.git.committed 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("state.git.committed")
        assert fmt is not None
        assert fmt.id == "state.git.committed"
        assert "anchor.hard" in fmt.tags
    
    def test_git_uncommitted_state_exists(self):
        """测试 state.git.uncommitted_changes 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("state.git.uncommitted_changes")
        assert fmt is not None
        assert fmt.id == "state.git.uncommitted_changes"
        assert "caution.required" in fmt.tags
    
    def test_tests_passing_state_exists(self):
        """测试 state.tests.passing 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("state.tests.passing")
        assert fmt is not None
        assert fmt.id == "state.tests.passing"
        assert "anchor.hard" in fmt.tags
    
    def test_tests_failing_state_exists(self):
        """测试 state.tests.failing 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("state.tests.failing")
        assert fmt is not None
        assert fmt.id == "state.tests.failing"
        assert "fix.required" in fmt.tags
    
    def test_state_types_have_caution_tags(self):
        """测试需要谨慎处理的状态类型有适当的标签"""
        registry = create_builtin_registry()
        
        caution_types = ["state.git.uncommitted_changes", "state.env.dirty"]
        for type_id in caution_types:
            fmt = registry.get(type_id)
            if fmt:
                assert "caution.required" in fmt.tags


class TestDebugTypes:
    """测试调试循环相关的语义类型"""
    
    def test_debug_hypothesis_type_exists(self):
        """测试 debug.hypothesis 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("debug.hypothesis")
        assert fmt is not None
        assert fmt.id == "debug.hypothesis"
        assert fmt.name == "DebugHypothesis"
        assert "phase.hypothesis" in fmt.tags
    
    def test_debug_breakpoint_log_type_exists(self):
        """测试 debug.breakpoint.log 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("debug.breakpoint.log")
        assert fmt is not None
        assert fmt.id == "debug.breakpoint.log"
        assert "phase.instrumentation" in fmt.tags
    
    def test_debug_execution_trace_type_exists(self):
        """测试 debug.execution.trace 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("debug.execution.trace")
        assert fmt is not None
        assert fmt.id == "debug.execution.trace"
        assert "phase.observe" in fmt.tags
    
    def test_debug_verification_result_type_exists(self):
        """测试 debug.verification.result 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("debug.verification.result")
        assert fmt is not None
        assert fmt.id == "debug.verification.result"
        assert "phase.verify" in fmt.tags
    
    def test_debug_types_form_workflow(self):
        """测试调试类型形成完整工作流"""
        registry = create_builtin_registry()
        
        # 调试工作流的各个阶段
        workflow_phases = [
            ("debug.hypothesis", "phase.hypothesis"),
            ("debug.breakpoint.log", "phase.instrumentation"),
            ("debug.execution.trace", "phase.observe"),
            ("debug.verification.result", "phase.verify"),
        ]
        
        for type_id, phase_tag in workflow_phases:
            fmt = registry.get(type_id)
            assert fmt is not None, f"Missing type: {type_id}"
            assert phase_tag in fmt.tags, f"Type {type_id} missing phase tag: {phase_tag}"


class TestUserModelTypes:
    """测试用户模型相关的语义类型"""
    
    def test_user_model_type_exists(self):
        """测试 user.model 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("user.model")
        assert fmt is not None
        assert fmt.id == "user.model"
        assert fmt.name == "UserModel"
        assert "content.model" in fmt.tags
    
    def test_user_preference_type_exists(self):
        """测试 user.preference 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("user.preference")
        assert fmt is not None
        assert fmt.id == "user.preference"
        assert fmt.name == "UserPreference"
        assert "content.preference" in fmt.tags
    
    def test_user_privacy_context_type_exists(self):
        """测试 user.privacy.context 类型存在"""
        registry = create_builtin_registry()
        fmt = registry.get("user.privacy.context")
        assert fmt is not None
        assert fmt.id == "user.privacy.context"
        assert fmt.name == "UserPrivacyContext"
        assert "sensitive" in fmt.tags



class TestArchitectureExtensions:
    """测试架构扩展的整体完整性"""
    
    def test_all_new_types_registered(self):
        """测试所有新增的语义类型都已注册"""
        registry = create_builtin_registry()
        
        new_types = [
            # 信息不足处理
            "info.insufficient",
            "kb.query.result",
            "assumption.proposal",
            "user.answer",
            
            # 状态类型
            "state.git.committed",
            "state.git.uncommitted_changes",
            "state.code.compiled",
            "state.tests.passing",
            "state.tests.failing",
            "state.env.dirty",
            
            # 调试类型
            "debug.hypothesis",
            "debug.breakpoint.log",
            "debug.execution.trace",
            "debug.verification.result",
            
            # 用户模型
            "user.model",
            "user.preference",
            "user.privacy.context",
        ]
        
        missing = []
        for type_id in new_types:
            fmt = registry.get(type_id)
            if fmt is None:
                missing.append(type_id)
        
        assert len(missing) == 0, f"Missing types: {missing}"
    
    def test_type_hierarchy_consistency(self):
        """测试类型层级一致性"""
        registry = create_builtin_registry()
        
        # 所有新增类型都应该是 requirement 或其子类型的后代
        def get_parent_chain(type_id: str, visited=None) -> list[str]:
            if visited is None:
                visited = set()
            if type_id in visited:
                return []
            visited.add(type_id)
            
            fmt = registry.get(type_id)
            if not fmt or not fmt.parent:
                return [type_id]
            
            return [type_id] + get_parent_chain(fmt.parent, visited)
        
        new_types = [
            "info.insufficient",
            "assumption.proposal",
            "state.git.committed",
            "debug.hypothesis",
            "user.model",
        ]
        
        for type_id in new_types:
            chain = get_parent_chain(type_id)
            assert "requirement" in chain, f"Type {type_id} not connected to requirement root"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
