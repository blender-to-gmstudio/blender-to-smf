# A couple of functions to make debugging easier
#

def format_iterable(iterable):
    formatted = ["{:4.4f}".format(item) for item in iterable]
    return "[" + ", ".join(formatted) + "]"

def print_dq_list(list, index_header, value_header):
    print(index_header, " - ", value_header)
    for i, dq in enumerate(list):
        print("{:2d}".format(i), " - ", format_iterable(dq))
