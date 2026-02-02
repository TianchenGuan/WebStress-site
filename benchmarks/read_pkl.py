#!/usr/bin/env python3
"""Read pickle files with missing module dependencies."""
import argparse
import pickle
import pprint


class SafeUnpickler(pickle.Unpickler):
    """
    Custom unpickler that handles missing modules by creating placeholder classes.
    """

    def find_class(self, module, name):
        """Override to handle missing modules."""
        try:
            return super().find_class(module, name)
        except (ModuleNotFoundError, AttributeError):
            # Create a placeholder class for missing modules
            class Placeholder:
                _module = module
                _name = name

                def __init__(self, *args, **kwargs):
                    self._args = args
                    self._kwargs = kwargs
                    self.__dict__.update(kwargs)

                def __repr__(self):
                    attrs = {k: v for k, v in self.__dict__.items()
                             if not k.startswith('_')}
                    return f"<{self._module}.{self._name}: {attrs}>"

                def __reduce__(self):
                    return (self.__class__, (), self.__dict__)

            Placeholder.__name__ = name
            Placeholder.__module__ = module
            return Placeholder


def read_pickle(file_path):
    """Read and return contents of a pickle file, handling missing modules."""
    with open(file_path, 'rb') as f:
        data = SafeUnpickler(f).load()
    return data


def format_data(data, max_depth=3):
    """Format data for display, handling nested structures."""
    if isinstance(data, dict):
        return {k: format_data(v, max_depth - 1) if max_depth > 0 else "..."
                for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        if len(data) > 10:
            return [format_data(x, max_depth - 1) for x in data[:5]] + [f"... ({len(data)} items)"]
        return [format_data(x, max_depth - 1) if max_depth > 0 else "..." for x in data]
    return data


def main():
    parser = argparse.ArgumentParser(description='Read a pickle file (handles missing modules)')
    parser.add_argument('path', help='Path to the pickle file')
    parser.add_argument('--raw', '-r', action='store_true', help='Show raw output without formatting')
    parser.add_argument('--keys', '-k', action='store_true', help='Show only top-level keys (if dict)')
    args = parser.parse_args()

    try:
        data = read_pickle(args.path)

        print(f"Type: {type(data).__name__}")
        print(f"Module: {type(data).__module__}")
        print()

        if args.keys and isinstance(data, dict):
            print("Keys:")
            for k in data.keys():
                v = data[k]
                print(f"  {k}: {type(v).__name__}")
        elif args.raw:
            print(data)
        else:
            print("Content:")
            pprint.pprint(format_data(data), width=120, depth=4)

        # If it has __dict__, show that too
        if hasattr(data, '__dict__') and data.__dict__:
            print("\nAttributes:")
            pprint.pprint(format_data(dict(data.__dict__)), width=120, depth=4)

    except FileNotFoundError:
        print(f"Error: File not found: {args.path}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")


if __name__ == '__main__':
    main()
