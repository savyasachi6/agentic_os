import sys

def validate_reward_function(code_string):
    """
    Mock validator to show how skills can bundle external tools.
    In a real system, you could check syntax, run pyflakes, or do static analysis.
    """
    if "def " not in code_string:
        print("Validation failed: No python function defined.")
        return False
    if "return " not in code_string:
        print("Validation failed: No return statement found.")
        return False
    
    print("Validation passed: Code string looks like a function.")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        code = sys.argv[1]
        validate_reward_function(code)
    else:
        print("Usage: python validate_reward.py 'def my_reward(): return 1'")
