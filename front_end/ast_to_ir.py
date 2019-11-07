import json
import re
from ir import *
from union_find import *

## The json dumper in ocaml seems to print <, >, and parentheses
## instead of {, }, [,]. Therefore we need to replace the characters
## with the correct ones.
def to_standard_json(string):
    string = string.replace("<", "{")
    string = string.replace(">", "}")
    string = string.replace("(", "[")
    string = string.replace(")", "]")

    # After these replacements, single names are written like this:
    # {"Name"} and the parser complains. We just need to remove the
    # braces.
    #
    # Note: I have noticed that the names are always constructors that
    # have no arguments, so they should all be letter characters.
    #
    # Warning: This is not robust at all, but will do for now
    string = re.sub(r'\{\"([A-Za-z]+)\"\}', r'"\1"', string)
    
    return string

## Returns the ast as a object
def parse_json_line(line):
    std_json_line = to_standard_json(line)        
    # print(std_json_line)
    ast_object = json.loads(std_json_line)
    return ast_object

## Returns a list of AST objects
def parse_json_ast(json_filename):
    with open(json_filename) as json_file:
        lines = json_file.readlines()
        ast_objects = [parse_json_line(line) for line in lines]
        # for ast_object in ast_objects:
            # print(json.dumps(ast_object, indent=2))
            # print(ast_object)
        return ast_objects

## Checks if the given ASTs are supported
def check_if_asts_supported(ast_objects):
    ## TODO: Implement
    return


## This combines all the children of the Pipeline to an IR, even
## though they might not be IRs themselves. This means that an IR
## might contain mixed commands and ASTs. The ASTs can be
## (conservatively) considered as stateful commands by default).
def combine_pipe(ast_nodes):
    ## Initialize the IR with the first node in the Pipe
    if (isinstance(ast_nodes[0], IR)):
        combined_nodes = ast_nodes[0]
    else:
        combined_nodes = IR([ast_nodes[0]])

    ## Combine the rest of the nodes
    for ast_node in ast_nodes[1:]:
        if (isinstance(ast_node, IR)):
            combined_nodes.pipe_append(ast_node)
        else:
            ## FIXME: This one will not work. The IR of an AST node
            ##        doesn't have any stdin or stdout.
            combined_nodes.pipe_append(IR([ast_node]))
            
    return [combined_nodes]


## For now these checks are too simple. 
##
## Maybe we can move them to the check_if_ast_is_supported?
def check_pipe(construct, arguments):
    assert(len(arguments) == 2)
    ## The pipe should have at least 2 children
    assert(len(arguments[1]) >= 2)

def check_command(construct, arguments):
    assert(len(arguments) == 4)

def check_and(construct, arguments):
    assert(len(arguments) == 2)

def check_or(construct, arguments):
    assert(len(arguments) == 2)

def check_semi(construct, arguments):
    assert(len(arguments) == 2)

def check_redir(construct, arguments):
    assert(len(arguments) == 3)

def check_subshell(construct, arguments):
    assert(len(arguments) == 3)

def check_background(construct, arguments):
    assert(len(arguments) == 3)

def check_defun(construct, arguments):
    assert(len(arguments) == 3)

def compile_arg_char(arg_char, fileIdGen):
    key, val = get_kv(arg_char)
    if (key == 'C'):
        return arg_char
    elif (key == 'B'):
        ## TODO: I probably have to redirect the input of the compiled
        ##       node (IR) to be closed, and the output to be
        ##       redirected to some file that we will use to write to
        ##       the command argument to complete the command
        ##       substitution.
        compiled_node = compile_node(val, fileIdGen)
        return {key : compiled_node}
    elif (key == 'Q'):
        compiled_val = compile_command_argument(val, fileIdGen)
        return {key : compiled_val}
    else:
        ## TODO: Complete this
        return arg_char
    
def compile_command_argument(argument, fileIdGen):
    compiled_argument = [compile_arg_char(char, fileIdGen) for char in argument]
    return compiled_argument
    
def compile_command_arguments(arguments, fileIdGen):
    compiled_arguments = [compile_command_argument(arg, fileIdGen) for arg in arguments]
    return compiled_arguments

## Compiles the value assigned to a variable using the command argument rules.
## TODO: Is that the correct way to handle them?
def compile_assignments(assignments, fileIdGen):
    compiled_assignments = [[assignment[0], compile_command_argument(assignment[1], fileIdGen)]
                            for assignment in assignments]
    return compiled_assignments
    
def compile_node(ast_node, fileIdGen):
    # print("Compiling node: {}".format(ast_node))

    construct, arguments = get_kv(ast_node)
    
    if (construct == 'Pipe'):
        check_pipe(construct, arguments)

        ## Note: Background indicates when the pipe should be run in the background.
        ##
        ## TODO: Investigate whether we can optimize more by running
        ##       the background pipes in a distributed fashion.
        background = arguments[0]
        pipe_items = arguments[1]

        compiled_pipe_nodes = combine_pipe([compile_node(pipe_item, fileIdGen)
                                            for pipe_item in pipe_items])

        if (len(compiled_pipe_nodes) == 1):
            ## Note: When calling combine_pipe_nodes (which
            ##       optimistically distributes all the children of a
            ##       pipeline) the compiled_pipe_nodes should always
            ##       be one IR
            compiled_ast = compiled_pipe_nodes[0]
        else:
            compiled_ast = {construct : [arguments[0]] + [compiled_pipe_nodes]}

    elif (construct == 'Command'):
        check_command(construct, arguments)

        ## TODO: Do we need the line number?
        
        ## If there are no arguments, the command is just an
        ## assignment
        if(len(arguments[2]) == 0):
            ## Just compile the assignments. Specifically compile the
            ## assigned values, because they might have command
            ## substitutions etc..
            assignments = arguments[1]
            compiled_assignments = compile_assignments(assignments, fileIdGen)
            compiled_ast = {construct : [arguments[0]] + [compiled_assignments] + [arguments[2:]]}
        else:
            command_name = arguments[2][0]
            options = compile_command_arguments(arguments[2][1:], fileIdGen)

            stdin_fid = fileIdGen.next_file_id()
            stdout_fid = fileIdGen.next_file_id()
            ## Question: Should we return the command in an IR if one of
            ## its arguments is a command substitution? Meaning that we
            ## will have to wait for its command to execute first?
            compiled_ast = IR([Command(command_name,
                                       stdin = stdin_fid,
                                       stdout = stdout_fid,
                                       options=options)],
                              stdin = stdin_fid,
                              stdout = stdout_fid)

    elif (construct == 'And'):
        check_and(construct, arguments)
        
        left_node = arguments[0]
        right_node = arguments[1]
        compiled_ast = {construct : [compile_node(left_node, fileIdGen),
                                     compile_node(right_node, fileIdGen)]}

    elif (construct == 'Or'):
        check_or(construct, arguments)
        
        left_node = arguments[0]
        right_node = arguments[1]
        compiled_ast = {construct : [compile_node(left_node, fileIdGen),
                                     compile_node(right_node, fileIdGen)]}
        
    elif (construct == 'Semi'):
        check_semi(construct, arguments)
        
        left_node = arguments[0]
        right_node = arguments[1]
        compiled_ast = {construct : [compile_node(left_node, fileIdGen),
                                     compile_node(right_node, fileIdGen)]}

    elif (construct == 'Redir'):
        check_redir(construct, arguments)

        line_no = arguments[0]
        node = arguments[1]
        redir_list = arguments[2]

        compiled_node = compile_node(node, fileIdGen)

        if (isinstance(compiled_node, IR)):
            ## TODO: I should use the redir list to redirect the files of
            ##       the IR accordingly
            compiled_ast = compiled_node
        else:
            compiled_ast = {construct : [line_no, compiled_node, redir_list]}

    elif (construct == 'Subshell'):
        check_subshell(construct, arguments)

        line_no = arguments[0]
        node = arguments[1]
        redir_list = arguments[2]

        compiled_node = compile_node(node, fileIdGen)

        ## Question: It seems that subshell can be handled exactly
        ##           like a redir. Is that true?

        ## TODO: Make sure that propagating the IR up, doesn't create
        ##       any issue.
        
        if (isinstance(compiled_node, IR)):
            ## TODO: I should use the redir list to redirect the files of
            ##       the IR accordingly
            compiled_ast = compiled_node
        else:
            compiled_ast = {construct : [line_no, compiled_node, redir_list]}
            
    elif (construct == 'Background'):
        check_background(construct, arguments)

        line_no = arguments[0]
        node = arguments[1]
        redir_list = arguments[2]

        compiled_node = compile_node(node, fileIdGen)
        
        ## TODO: I should use the redir list to redirect the files of
        ##       the IR accordingly
        if (isinstance(compiled_node, IR)):
            ## TODO: Redirect the stdout, stdin accordingly
            compiled_ast = compiled_node
        else:
            ## Note: It seems that background nodes can be added in
            ##       the distributed graph similarly to the children
            ##       of pipelines.
            ##
            ## Question: What happens with the stdin, stdout. Should
            ## they be closed?
            compiled_ast = IR([compiled_node])

    elif (construct == 'Defun'):
        check_defun(construct, arguments)
        
        ## It is not clear how we should handle functions.
        ##
        ## - Should we transform their body to IR?
        ## - Should we handle calls to the functions as commands?
        ##
        ## It seems that we should do both. But we have to think if
        ## this introduces any possible problem.

        line_no = arguments[0]
        name = arguments[1]
        body = arguments[2]

        ## TODO: Investigate whether it is fine to just compile the
        ##       body of functions.
        compiled_body = compile_node(body, fileIdGen)
        compiled_ast = {construct : [line_no, name, compiled_body]}
        
    else:
        raise TypeError("Unimplemented construct: {}".format(construct))

    # print("Compiled node: {}".format(compiled_ast))
    return compiled_ast

## Compiles a given AST to an intermediate representation tree, which
## has some subtrees in it that are graphs representing a distributed
## computation.
##
## The above assumes that subtrees of the AST are disjoint
## computations that can be distributed separately (locally/modularly)
## without knowing about previous or later subtrees that can be
## distributed. Is that reasonable?
def compile_ast(ast_object, fileIdGen):
    compiled_ast = compile_node(ast_object, fileIdGen)
    return compiled_ast
