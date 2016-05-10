'''
categorize amr; generate linearized amr sequence
'''
import sys, os, re, codecs
from amr_graph import AMR
from collections import OrderedDict, defaultdict
from constants import TOP,LBR,RBR,RET,SURF,END
import gflags
from parser import ParserError
FLAGS=gflags.FLAGS

class AMR_stats(object):
    def __init__(self):
        self.num_reentrancy = 0
        self.num_predicates = defaultdict(int)
        self.num_nonpredicate_vals = defaultdict(int)
        self.num_consts = defaultdict(int)
        self.num_entities = defaultdict(int)
        self.num_named_entities = defaultdict(int)

    def collect_stats(self, amrs):
        for amr in amrs:
            named_entity_nums, entity_nums, predicate_nums, variable_nums, const_nums, reentrancy_nums = amr.statistics()

            self.update(reentrancy_nums, predicate_nums, variable_nums, const_nums, entity_nums, named_entity_nums)

    def update(self, local_re, local_pre, local_non, local_con, local_ent, local_ne):
        self.num_reentrancy += local_re
        for s in local_pre:
            self.num_predicates[s] += local_pre[s]

        for s in local_non:
            self.num_nonpredicate_vals[s] += local_non[s]

        for s in local_con:
            self.num_consts[s] += local_con[s]

        for s in local_ent:
            self.num_entities[s] += local_ent[s]

        for s in local_ne:
            self.num_named_entities[s] += local_ne[s]

    def dump2dir(self, dir):
        def dump_file(f, dict):
            sorted_dict = sorted(dict.items(), key=lambda k:(-k[1], k[0]))
            for (item, count) in sorted_dict:
                print >>f, '%s %d' % (item, count)
            f.close()

        pred_f = open(os.path.join(dir, 'pred'), 'w')
        non_pred_f = open(os.path.join(dir, 'non_pred_val'), 'w')
        const_f = open(os.path.join(dir, 'const'), 'w')
        entity_f = open(os.path.join(dir, 'entities'), 'w')
        named_entity_f = open(os.path.join(dir, 'named_entities'), 'w')

        dump_file(pred_f, self.num_predicates)
        dump_file(non_pred_f, self.num_nonpredicate_vals)
        dump_file(const_f, self.num_consts)
        dump_file(entity_f, self.num_entities)
        dump_file(named_entity_f, self.num_named_entities)

    def __str__(self):
        s = ''
        s += 'Total number of reentrancies: %d\n' % self.num_reentrancy
        s += 'Total number of predicates: %d\n' % len(self.num_predicates)
        s += 'Total number of non predicates variables: %d\n' % len(self.num_nonpredicate_vals)
        s += 'Total number of constants: %d\n' % len(self.num_consts)
        s += 'Total number of entities: %d\n' % len(self.num_entities)
        s += 'Total number of named entities: %d\n' % len(self.num_named_entities)
        return s


class AMR_seq:
    def __init__(self):
        pass

    def linearize_amr(self, amr):
        '''
        given an amr graph, output a linearized and categorized amr sequence;
        TODO: use dfs prototype
        '''
        #pass
        r = amr.roots[0] # single root assumption
        old_depth = -1
        depth = -1
        stack = [(r,TOP,None,0)]
        aux_stack = []
        seq = []

        while stack:
            old_depth = depth
            cur_var, rel, parent, depth = stack.pop()
            #exclude_rels = []

            i = 0
            #print seq
            #print stack
            #print aux_stack
            while old_depth - depth >= i:
                if aux_stack == []:
                    import pdb
                    pdb.set_trace()
                seq.append(aux_stack.pop())
                i+=1


            if (parent, rel, cur_var) in amr.reentrance_triples:
                #seq.extend([rel+LBR,RET,RBR+rel])
                seq.append(rel+LBR)
                seq.append(RET)
                aux_stack.append(RBR+rel)
                continue

            seq.append(rel+LBR)
            exclude_rels, cur_symbol = self.get_symbol(cur_var, amr)
            seq.append(cur_symbol)
            aux_stack.append(RBR+rel)

            for rel, var in reversed(amr[cur_var].items()):
                if rel not in exclude_rels:
                    stack.append((var[0],rel,cur_var,depth+1))

        seq.extend(aux_stack[::-1])
        seq.append(END)

        return seq

    def restore_amr(self, amrseq):
        '''
        Given a linearized amr sequence, restore its amr graph
        Deal with non-matching parenthesis
        '''
        def rebuild_seq(parsed_seq):
            new_seq = []
            stack = []

            while parsed_seq[-1][1] == "LPAR": #Delete the last few left parenthesis
                parsed_seq = parsed_seq[:-1]

            assert len(parsed_seq) > 0, parsed_seq
            for (token, type) in parsed_seq:
                if type == "LPAR": #Left parenthesis
                    if stack and stack[-1][1] == "LPAR":
                        new_token = 'ROOT'
                        new_type = 'NONPRED'
                        stack.append((new_token, new_type))
                        new_seq.append((new_token, new_type))

                    stack.append((token, type))
                    new_seq.append((token, type))
                elif type == "RPAR": #Right parenthesis
                    assert stack
                    if stack[-1][1] == "LPAR": #No concept for this edge, remove
                        stack.pop()
                        new_seq.pop()
                    elif stack[-2][0][:-1] == '-TOP-':
                        continue
                    else:
                        stack.pop()
                        ledgelabel, ltype = stack.pop()
                        try:
                            assert ltype == "LPAR", ('%s %s'% (ledgelabel, ltype))
                        except:
                            print stack
                            print ledgelabel, ltype
                            print token, type
                            sys.exit(1)
                        redgelabel = ')%s' % (ledgelabel[:-1])
                        new_seq.append((redgelabel, "RPAR"))
                else:
                    if stack[-1][1] == "LPAR":
                        stack.append((token, type))
                        new_seq.append((token, type))
            while stack:
                while stack[-1][1] == "LPAR" and stack:
                    stack.pop()

                if not stack:
                    break

                stack.pop()
                ledgelabel, ltype = stack.pop()
                assert ltype == "LPAR"
                redgelabel = ')%s' % (ledgelabel[:-1])
                new_seq.append((redgelabel, "RPAR"))

            return new_seq

        def make_compiled_regex(rules):
            regexstr =  '|'.join('(?P<%s>%s)' % (name, rule) for name, rule in rules)
            return re.compile(regexstr)

        def register_var(token):
            num = 0
            while True:
                currval = '%s%d' % (token[0], num)
                if currval in var_set:
                    num += 1
                else:
                    var_set.add(currval)
                    return currval

        amr = AMR()
        seq = amrseq.strip().split()
        triples = []

        stack = []
        state = 0
        node_idx = 0; # sequential new node index
        mapping_table = {};  # old new index mapping table

        var_set = set()

        const_set = set(['interrogative', 'imperative', 'expressive', '-'])
        lex_rules = [
            ("LPAR", '[^\s()]+\('),  #Start of an edge
            ("RPAR",'\)[^\s()]+'),  #End of an edge
            ("SURF", '-SURF-'),  #Surface form constant
            ("POLARITY", '-'),
            ("REENTRANCY", '-RET-'),  #Reentrancy
            ("ENTITY", 'ENT_([^\s()]+)'),  #Entity
            ("NER", 'NE_([^\s()]+)'), #Named entity
            ("PRED", '([^\s()]+)-[0-9]+'), #Predicate
            ("NONPRED", '([^\s()]+)')  #Non predicate variables
        ]

        token_re = make_compiled_regex(lex_rules)

        parsed_seq = []
        for match in token_re.finditer(amrseq):
            token = match.group()
            type = match.lastgroup
            parsed_seq.append((token, type))

        PNODE = 1
        CNODE = 2
        LEDGE = 3
        REDGE = 4
        RCNODE = 5
        parsed_seq = rebuild_seq(parsed_seq)

        token_seq = [token for (token, type) in parsed_seq]

        seq_length = len(parsed_seq)
        for (currpos, (token, type)) in enumerate(parsed_seq):
            if state == 0: #Start state
                assert type == "LPAR", ('start with symbol: %s' % token)
                edgelabel = token[:-1]
                stack.append((LEDGE, edgelabel))
                state = 1

            elif state == 1: #Have just identified an left edge, next expect a concept
                if type == "NER":
                    nodelabel = register_var(token)
                    nodeconcept = token
                    stack.append((PNODE,nodelabel,nodeconcept))
                    state = 2
                elif type == "ENTITY":
                    nodelabel = register_var(token)
                    nodeconcept = token
                    stack.append((PNODE,nodelabel,nodeconcept))
                    state = 2
                elif type == "PRED":
                    nodelabel = register_var(token)
                    nodeconcept = token
                    stack.append((PNODE,nodelabel,nodeconcept))
                    state = 2
                elif type == "NONPRED":
                    nodelabel = register_var(token)
                    nodeconcept = token
                    stack.append((PNODE,nodelabel,nodeconcept))
                    state = 2
                elif type == "SURF":
                    stack.append((PNODE,token.strip(),None))
                    state = 2
                elif type == "REENTRANCY":
                    if currpos + 1 < seq_length and parsed_seq[currpos+1][1] == "LPAR":
                        nodelabel = register_var(token)
                        nodeconcept = token
                        stack.append((PNODE,nodelabel,nodeconcept))
                    else:
                        stack.append((PNODE,token.strip(),None))
                    state = 2
                elif type == "POLARITY":
                    stack.append((PNODE,token.strip(),None))
                    state = 2
                else: raise ParserError , "Unexpected token %s"%(token.encode('utf8'))

            elif state == 2: #Have just identified a PNODE concept
                if type == "LPAR":
                    edgelabel = token[:-1]
                    stack.append((LEDGE, edgelabel))
                    state = 1
                elif type == "RPAR":
                    assert stack[-1][0] == PNODE
                    forgetme, nodelabel, nodeconcept = stack.pop()
                    if not nodelabel in amr.node_to_concepts and nodeconcept is not None:
                        amr.node_to_concepts[nodelabel] = nodeconcept

                    foo = amr[nodelabel]
                    if stack and stack[-1][1] != "-TOP-": #This block needs to be updated
                        stack.append((CNODE, nodelabel, nodeconcept))
                        state = 3
                    else: #Single concept AMR
                        assert len(stack) == 1 and stack[-1][1] == "-TOP-", "Not start with TOP"
                        stack.pop()
                        if amr.roots:
                            break
                        amr.roots.append(nodelabel)
                        state = 0
                        #break
                else: raise ParserError, "Unexpected token %s"%(token)

            elif state == 3: #Have just finished a CNODE, which means wrapped up with one branch
                if type == "LPAR":
                    edgelabel = token[:-1]
                    stack.append((LEDGE, edgelabel))
                    state = 1

                elif type == "RPAR":
                    edges = []
                    while stack[-1][0] != PNODE:
                        children = []
                        assert stack[-1][0] == CNODE, "Expect a parsed node but none found"
                        forgetme, childnodelabel, childconcept = stack.pop()
                        children.append((childnodelabel,childconcept))

                        assert stack[-1][0] == LEDGE, "Found a non-left edge"
                        forgetme, edgelabel = stack.pop()

                        edges.append((edgelabel,children))

                    forgetme,parentnodelabel,parentconcept = stack.pop()

                    #check for annotation error
                    if parentnodelabel in amr.node_to_concepts:
                        print parentnodelabel, parentconcept
                        assert parentconcept is not None
                        if amr.node_to_concepts[parentnodelabel] == parentconcept:
                            sys.stderr.write("Wrong annotation format: Revisited concepts %s should be ignored.\n" % parentconcept)
                        else:
                            sys.stderr.write("Wrong annotation format: Different concepts %s and %s have same node label(index)\n" % (amr.node_to_concepts[parentnodelabel],parentconcept))
                            parentnodelabel = parentnodelabel + "1"


                    if not parentnodelabel in amr.node_to_concepts and parentconcept is not None:
                        amr.node_to_concepts[parentnodelabel] = parentconcept

                    for edgelabel,children in reversed(edges):
                        hypertarget = []
                        for node, concept in children:
                            if node is not None and not node in amr.node_to_concepts and concept:
                                amr.node_to_concepts[node] = concept
                            hypertarget.append(node)
                        hyperchild = tuple(hypertarget)
                        amr._add_triple(parentnodelabel,edgelabel,hyperchild)

                    if stack and stack[-1][1] != "-TOP-": #we have done with current level
                        state = 3
                        stack.append((CNODE, parentnodelabel, parentconcept))
                    else: #Single concept AMR
                        assert len(stack) == 1 and stack[-1][1] == "-TOP-", "Not start with TOP"
                        stack.pop()
                        if amr.roots:
                            break
                        amr.roots.append(parentnodelabel)
                        state = 0
                        break
                        #state = 0
                        #amr.roots.append(parentnodelabel)
                else: raise ParserError, "Unexpected token %s"%(token.encode('utf8'))

        if state != 0 and stack:
            raise ParserError, "mismatched parenthesis"
        return amr

    def get_symbol(self, var, amr):
        if amr.is_named_entity(var):
            exclude_rels = ['wiki','name']
            entity_name = amr.node_to_concepts[var]
            return exclude_rels, 'NE_'+entity_name
        elif amr.is_entity(var):
            entity_name = amr.node_to_concepts[var]
            return [], 'ENT_'+entity_name
        elif amr.is_predicate(var):
            pred_name = amr.node_to_concepts[var]
            return [], pred_name
        elif amr.is_const(var):
            if var in ['interrogative', 'imperative', 'expressive', '-']:
                return [], var
            else:
                return [], SURF

        else:
            variable_name = amr.node_to_concepts[var]
            return [], variable_name

        return [],var






def readAMR(amrfile_path):
    amrfile = codecs.open(amrfile_path,'r',encoding='utf-8')
    #amrfile = open(amrfile_path,'r')
    comment_list = []
    comment = OrderedDict()
    amr_list = []
    amr_string = ''

    for line in amrfile.readlines():
        if line.startswith('#'):
            for m in re.finditer("::([^:\s]+)\s(((?!::).)*)",line):
                #print m.group(1),m.group(2)
                comment[m.group(1)] = m.group(2)
        elif not line.strip():
            if amr_string and comment:
                comment_list.append(comment)
                amr_list.append(amr_string)
                amr_string = ''
                comment = {}
        else:
            amr_string += line.strip()+' '

    if amr_string and comment:
        comment_list.append(comment)
        amr_list.append(amr_string)
    amrfile.close()

    return (comment_list,amr_list)

def amr2sequence(toks, amr_graphs, out_seq_file):
    amr_seq = AMR_seq()
    with open(out_seq_file, 'w') as outf:
        print 'Linearizing ...'
        for i,g in enumerate(amr_graphs):
            print 'No ' + str(i) + ':' + ' '.join(toks[i])
            seq = ' '.join(amr_seq.linearize_amr(g))
            print >> outf, seq

def sequence2amr(toks, amrseqs, out_amr_file):
    amr_seq = AMR_seq()
    with open(out_amr_file, 'w') as outf:
        print 'Restoring AMR graphs ...'
        for i,s in enumerate(amrseqs):
            print 'No ' + str(i) + ':' + ' '.join(toks[i])
            restored_amr = amr_seq.restore_amr(s)
            print >> outf, restored_amr.to_amr_string()
            print >> outf, ''
        outf.close()

if __name__ == "__main__":
    gflags.DEFINE_string("data_dir",'../train',"data directory")
    gflags.DEFINE_string("amrseq_file",'../dev.decode.amrseq',"amr sequence file")
    gflags.DEFINE_string("amr_result_file",'../dev.decode.amr',"result amr file")
    gflags.DEFINE_string("seq_result_file",'../dev.decode.amr',"result amr sequence file")
    gflags.DEFINE_boolean("seq2amr", False, "If sequence to amr")
    gflags.DEFINE_boolean("amr2seq", False, "If amr to sequenc")
    argv = FLAGS(sys.argv)

    amr_file = os.path.join(FLAGS.data_dir, 'amr')

    alignment_file = os.path.join(FLAGS.data_dir, 'alignment')
    sent_file = os.path.join(FLAGS.data_dir, 'sentence')
    tok_file = os.path.join(FLAGS.data_dir, 'token')
    pos_file = os.path.join(FLAGS.data_dir, 'pos')

    comment_list, amr_list = readAMR(amr_file)
    #amr_graphs = [AMR.parse_string(amr_string) for amr_string in amr_list]
    amrseqs = [line.strip() for line in open(FLAGS.amrseq_file, 'r')]
    alignments = [line.strip().split() for line in open(alignment_file, 'r')]
    sents = [line.strip().split() for line in open(sent_file, 'r')]
    toks = [line.strip().split() for line in open(tok_file, 'r')]
    #lemmas = [line.strip().split() for line in open(lemma_file, 'r')]
    poss = [line.strip().split() for line in open(pos_file, 'r')]
    if FLAGS.seq2amr:
        sequence2amr(toks, amrseqs, FLAGS.amr_result_file)

    if FLAGS.amr2seq:
        amr2sequence(toks, amr_graphs, FLAGS.seq_result_file)

    ##################
    # get statistics
    ##################
    # amr_stats = AMR_stats()
    # amr_stats.collect_stats(amr_graphs)
    # print amr_stats
    # amr_stats.dump2dir(FLAGS.data_dir)

    # print toks[1]
    # print amr_graphs[1].to_amr_string()
    # amr_seq = AMR_seq()
    # print ' '.join(amr_seq.linearize_amr(amr_graphs[1]))
    #out_seq_file = os.path.join(FLAGS.data_dir, 'amrseq')
    #test_seq = '-TOP-( multi-sentence snt1( look-01 ARG0( we )ARG0 ARG1( place ARG1-of( look-01 ARG0( we )ARG0 )ARG1-of quant( many )quant ARG1-of( let-01 ARG0( we )ARG0 time( before op1( now )op1 quant( many op1( ENT_temporal-quantity quant( -SURF- )quant unit( year )unit )op1 )quant )time )ARG1-of )ARG1 ARG2( die-01 ARG1-of( look-01 ARG0( -RET- )ARG0 )ARG1-of )ARG2 time( before op1( now )op1 quant( many op1( ENT_temporal-quantity quant( -SURF- )quant unit( year )unit )op1 )quant )time )-TOP-'
    #amr_seq = AMR_seq()
    #out_seq_file = 'amrseq_test'
    #restored_amr = amr_seq.restore_amr(test_seq)
    #print restored_amr.to_amr_string()
    #with open(out_seq_file, 'w') as outf:
    #    print 'Linearizing ...'
    #    for i,g in enumerate(amr_graphs):
    #        print 'No ' + str(i) + ':' + ' '.join(toks[i])
    #        #print amr_graphs[i].to_amr_string()
    #        seq = ' '.join(amr_seq.linearize_amr(g))
    #        #ourf.write(seq)
    #        print >> outf, seq

    #for decode_line in amrseqs:
    #    restored_amr = amr_seq.restore_amr(decode_line)
    #    print restored_amr.to_amr_string()
    #    print ''


