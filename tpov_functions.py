# This file contains functions used by other programs. It should not be run directly.

# Built-in modules
import shutil

# Third-party modules
from texttable import Texttable

def renamedict (d, assignments: dict):
    return type (d) ((assignments.get (k, k), v) for k, v in d.items ())

def listsel (ls, prompt: str, min_len: int = 0, max_len: int = 0):
    # A rough implementation, could be improved with a proper parser
    prompt, args, count, indices, num, reverse = prompt.split (), ["+"], 0, set (), False, False
    while count < len (prompt):
        if count == 0 and prompt [0].lower () in ("rev", "all", "revall"):
            if prompt [0].lower ().startswith ("rev"):
                reverse = True
            if prompt [0].lower ().endswith ("all"):
                args.append (range (len (ls)))
                num = True
            count += 1
            continue
        if prompt [count].lower () == "to":
            if prompt [count - 2].lower () == "to":
                raise ValueError ("Two consecutive 'to' operators.")
            args.pop ()
            if prompt [count + 1].isdigit ():
                to_range = sorted ((int (prompt [count - 1]), int (prompt [count + 1])))
            else:
                raise ValueError (f"Invalid input '{prompt [count + 1]}'.")
            if any (i >= len (ls) for i in to_range):
                raise ValueError ("Range must be within the list.")
            to_range [1] += 1
            args.append (range (*to_range))
            count += 1
            num = False
        elif prompt [count] in ["+", "-"]:
            if len (args) % 2 == 1:
                raise ValueError ("Two consecutive operators.")
            args.append (prompt [count])
            num = False
        elif prompt [count].isdigit ():
            if int (prompt [count]) >= len (ls):
                raise ValueError ("Index must be within the list.")
            if num:
                raise ValueError ("Two consecutive literals.")
            args.append (range (int (prompt [count]), int (prompt [count]) + 1))
            num = True
        else:
            raise ValueError (f"Invalid input '{prompt [count]}'.")
        count += 1
    for i, j in zip (args [ : : 2], args [1 : : 2]):
        if i == "+":
            indices.update (j)
        elif i == "-":
            indices.difference_update (j)
    if min_len and len (indices) < min_len:
        raise ValueError (f"Selection is less than minimum length of {min_len}.")
    if max_len and len (indices) > max_len:
        raise ValueError (f"Selection exceeds maximum length of {max_len}.")
    if reverse:
        return (j for i, j in enumerate (reversed (ls)) if len (ls) - i - 1 in indices)
    return (j for i, j in enumerate (ls) if i in indices)

def choice (ls, question: str, min_len: int = 0, max_len: int = 0):
    while True:
        try:
            return listsel (ls, input (question), min_len, max_len)
        except Exception as e:
            print ("Error parsing list selection:", e)

def choicetable (header, data):
    display = Texttable (max_width = shutil.get_terminal_size ().columns)
    display.set_deco (Texttable.HEADER)
    display.set_cols_align (["l"] + ["l"] * len (header))
    display.set_cols_dtype (["i"] + ["t"] * len (header))
    display.header (["#"] + list (header))
    for j, i in enumerate (data):
        display.add_row ([j] + list (i))
    print (display.draw ())

if __name__ == "__main__":
    raise SystemExit ("This file contains functions used by other programs. It should not be run directly.")