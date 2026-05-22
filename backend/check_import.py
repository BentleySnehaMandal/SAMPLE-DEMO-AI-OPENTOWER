import traceback
import sys
sys.path.insert(0, '.')
try:
    import main
    print("main imported OK")
except Exception as e:
    traceback.print_exc()
