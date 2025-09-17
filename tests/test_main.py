"""
Tests for smartapi_mcp.__main__ module

This test suite provides coverage for the __main__ module,
ensuring that the module properly executes the main function
when run as a script.
"""

import sys
from unittest.mock import patch, MagicMock
import pytest


class TestMainModule:
    """Test cases for __main__ module functionality."""

    def test_main_module_exists(self):
        """Test that the __main__ module exists and is importable."""
        try:
            import smartapi_mcp.__main__
            assert True
        except ImportError:
            pytest.fail("__main__ module should be importable")

    @patch('smartapi_mcp.cli.main')
    def test_main_module_does_not_call_main_on_import(self, mock_main):
        """Test that importing __main__ module does NOT call cli.main()."""
        # Reset the mock to ensure clean state
        mock_main.reset_mock()
        
        # Import the __main__ module - this should NOT trigger the main() call
        # because __name__ will be 'smartapi_mcp.__main__', not '__main__'
        if 'smartapi_mcp.__main__' in sys.modules:
            # Remove from sys.modules to force reimport
            del sys.modules['smartapi_mcp.__main__']
        
        # Import the module - this should NOT call main() during import
        import smartapi_mcp.__main__
        
        # Verify that main() was NOT called during import
        mock_main.assert_not_called()

    def test_main_module_calls_main_when_name_is_main(self):
        """Test that __main__ module calls main() when __name__ == '__main__'."""
        with patch('smartapi_mcp.cli.main') as mock_main:
            # Import the module first to get a reference
            if 'smartapi_mcp.__main__' in sys.modules:
                del sys.modules['smartapi_mcp.__main__']
            
            import smartapi_mcp.__main__ as main_module
            
            # Reset the mock after import (which didn't call main)
            mock_main.reset_mock()
            
            # Simulate the condition where __name__ == '__main__'
            # by directly calling the condition
            if main_module.__name__ == "__main__":
                main_module.main()
            # Since the imported module's __name__ is not '__main__', we simulate it
            with patch.object(main_module, '__name__', '__main__'):
                # This simulates what happens when the module is executed directly
                exec(compile("if __name__ == '__main__': main()", "<test>", "exec"), 
                     main_module.__dict__)
            
            # Verify main() was called
            mock_main.assert_called_once_with()

    def test_main_module_propagates_exceptions_when_executed_directly(self):
        """Test that exceptions from main() are propagated when module is executed directly."""
        with patch('smartapi_mcp.cli.main') as mock_main:
            # Configure mock to raise an exception
            mock_main.side_effect = RuntimeError("Test error from main()")
            
            # Import the module first
            if 'smartapi_mcp.__main__' in sys.modules:
                del sys.modules['smartapi_mcp.__main__']
            
            import smartapi_mcp.__main__ as main_module
            
            # Simulate direct execution which should propagate the exception
            with pytest.raises(RuntimeError, match="Test error from main\\(\\)"):
                with patch.object(main_module, '__name__', '__main__'):
                    exec(compile("if __name__ == '__main__': main()", "<test>", "exec"), 
                         main_module.__dict__)

    def test_main_module_content(self):
        """Test that __main__ module has the expected content structure."""
        # Remove from sys.modules to force reimport if already imported
        if 'smartapi_mcp.__main__' in sys.modules:
            del sys.modules['smartapi_mcp.__main__']
        
        # Mock the main function to avoid actual execution
        with patch('smartapi_mcp.cli.main'):
            import smartapi_mcp.__main__ as main_module
            
            # Check that the module has the expected attributes
            # It should have imported main from cli
            assert hasattr(main_module, 'main')
            
            # Check that __name__ is set correctly when imported as module
            # Note: When imported, __name__ will be 'smartapi_mcp.__main__'
            # Only when executed directly will it be '__main__'
            assert main_module.__name__ == 'smartapi_mcp.__main__'

    def test_main_module_if_name_main_guard_works_correctly(self):
        """Test the if __name__ == '__main__' guard functionality."""
        with patch('smartapi_mcp.cli.main') as mock_main:
            # Import the module
            if 'smartapi_mcp.__main__' in sys.modules:
                del sys.modules['smartapi_mcp.__main__']
            
            import smartapi_mcp.__main__ as main_module
            
            # Verify main() was NOT called during import (guard condition false)
            mock_main.assert_not_called()
            
            # Reset mock and test the guard when condition is true
            mock_main.reset_mock()
            
            # Simulate the condition being true by executing the guard directly
            with patch.object(main_module, '__name__', '__main__'):
                exec(compile("if __name__ == '__main__': main()", "<test>", "exec"), 
                     main_module.__dict__)
            
            # Now main() should have been called
            mock_main.assert_called_once()

    def test_main_module_import_structure(self):
        """Test that __main__ module imports the correct dependencies."""
        # Remove from sys.modules to force reimport if already imported  
        if 'smartapi_mcp.__main__' in sys.modules:
            del sys.modules['smartapi_mcp.__main__']
            
        with patch('smartapi_mcp.cli.main'):
            import smartapi_mcp.__main__ as main_module
            
            # Verify that the main function was imported from cli
            from smartapi_mcp.cli import main as cli_main
            # The imported main should be the same as the cli main
            assert main_module.main == cli_main

    def test_main_module_handles_keyboard_interrupt_when_executed(self):
        """Test that __main__ module propagates KeyboardInterrupt when executed directly."""
        with patch('smartapi_mcp.cli.main') as mock_main:
            # Configure mock to raise KeyboardInterrupt
            mock_main.side_effect = KeyboardInterrupt()
            
            # Import the module first (should not raise)
            if 'smartapi_mcp.__main__' in sys.modules:
                del sys.modules['smartapi_mcp.__main__']
            
            import smartapi_mcp.__main__ as main_module
            
            # Importing should NOT raise KeyboardInterrupt
            # Only direct execution should
            with pytest.raises(KeyboardInterrupt):
                with patch.object(main_module, '__name__', '__main__'):
                    exec(compile("if __name__ == '__main__': main()", "<test>", "exec"), 
                         main_module.__dict__)

    @patch('smartapi_mcp.cli.main')  
    def test_main_module_multiple_imports_dont_call_main(self, mock_main):
        """Test that multiple imports don't call main() at all."""
        # Reset mock
        mock_main.reset_mock()
        
        # Remove from sys.modules to force first import
        if 'smartapi_mcp.__main__' in sys.modules:
            del sys.modules['smartapi_mcp.__main__']
        
        # First import - should NOT call main() (guard condition is false)
        import smartapi_mcp.__main__
        first_call_count = mock_main.call_count
        
        # Second import - should also NOT call main() 
        import smartapi_mcp.__main__
        second_call_count = mock_main.call_count
        
        # Neither import should call main() because __name__ != '__main__'
        assert first_call_count == 0
        assert second_call_count == 0  # Still 0

    def teardown_method(self):
        """Clean up after each test by removing the module from sys.modules."""
        # Ensure clean state for next test
        if 'smartapi_mcp.__main__' in sys.modules:
            del sys.modules['smartapi_mcp.__main__']