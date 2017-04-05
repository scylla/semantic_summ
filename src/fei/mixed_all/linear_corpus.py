#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import codecs
import pickle
import argparse

from collections import namedtuple
from amr_graph import AmrEdge
from amr_graph import AmrGraph
from amr_graph import NodeSource, EdgeSource
from utils import getLogger
from utils import Queue

logger = getLogger()

Instance = namedtuple('Instance', 'filename, nodes, edges, gold')
_EMPTY = "_EMPTY"
_SPACE = " "
_BLANK = ''


class GlobalNodeEdgeInfo(object):
    def __init__(self):
        self.node_labels = {} # int to string map
        self.inverse_node_labels = {} # invert node labels
        self.edge_labels = {} # tuple to string map
        self.edge_relations = {} # list of all egde relations possible and received from data
        self.node_idx = 0
        self.edges_idx = 0
        return

    def get_sorted_relations_list(self):
        relations_list = [key for key in sorted(self.edge_relations)]
        return relations_list

    def get_attribute_dict(self):
        attribute_dict = {}
        for key in self.edge_relations:
            if key.find('-of') == -1:
                attribute_dict[key] = _EMPTY
        return attribute_dict

class CorpusNode(object):
    def __init__(self):
        self.summ_data = []
        self.sentence_data = []
        self.summ_amrs = []
        self.sentence_amrs = []
    def appendSummText(self, data):
        self.summ_data.append(data)
    def appendSentenceText(self, data):
        self.sentence_data.append(data)
    def appendSummAmr(self, data):
        self.summ_amrs.append(data)
    def appendSentenceAmr(self, data):
        self.sentence_amrs.append(data)

# global edge node info
global_info = GlobalNodeEdgeInfo()
text_graph_dict = {} # all linearized graph representations

class NodeProperties(object):
    def __init__(self):
        self.adjacency_list = []
        self.is_root = False
        return

class TextGraph(object):
    def __init__(self):
        return

    def createGraph(self, edge_list, nodes):
        self.graph = {} # dictionary of node properties
        self.roots = [] # sentence roots for current graph

        # update adjacency list
        for k_edge, v_edge in edge_list.iteritems():
            if k_edge[0] not in self.graph:
                self.graph[k_edge[0]] = NodeProperties()
            if k_edge[1] not in self.graph:
                self.graph[k_edge[1]] = NodeProperties()

            self.graph[k_edge[0]].adjacency_list.append((k_edge[1], v_edge.relation))

        all_nodes, _, root_nodes = nodes

        # update root nodes
        for r_node in root_nodes:
            if r_node[0] not in self.graph:
                self.graph[r_node[0]] = NodeProperties()
            self.graph[r_node[0]].is_root = True
            self.roots.append(r_node[0])

    # return linearized representation
    def linearize_level_ordered(self, level = 1):
        graph_str = ''
        bfs_queue = Queue()
        cur_level_count = 0
        visited = {key:False for key in self.graph}

        for root in self.roots:
            bfs_queue.enqueue(root)
            cur_level_count += 1

        while not bfs_queue.isEmpty() and level > 0:
            next_level_count = 0
            while cur_level_count > 0:
                cur_item = bfs_queue.dequeue()
                if not visited[cur_item]:
                    visited[cur_item] = True
                    if global_info.node_labels[cur_item].find('name_') != -1 or global_info.node_labels[cur_item].find('date-entity') != -1: # skip name and date entity as global concepts
                        cur_level_count -= 1
                        continue
                    graph_str += global_info.node_labels[cur_item] + _SPACE
                    for neighbour in self.graph[cur_item].adjacency_list:
                        next_level_count += 1
                        bfs_queue.enqueue(neighbour[0])

                cur_level_count -= 1
            cur_level_count = next_level_count
            level -= 1

        return graph_str

    def linearize_depth_ordered(self, depth = 1):
        return

    def linearize_amr_graphs(self):
        for root in self.roots:
            linear_out = self.linearize_amr_graph(root, _EMPTY, True)
            linear_out = _SPACE.join(linear_out.split())
            print linear_out
        return

    # depth first amr linearization
    def linearize_amr_graph(self, cur_node, p_edge, is_root):
        linearized_graph_rep = ''
        if is_root:
            linearized_graph_rep += "--TOP( " + global_info.node_labels[cur_node] + _SPACE
        else:
            linearized_graph_rep += p_edge + "( " + global_info.node_labels[cur_node] + _SPACE
        for neighbour in self.graph[cur_node].adjacency_list:
            linearize_amr_child = self.linearize_amr_graph(neighbour[0], neighbour[1], False)
            linearized_graph_rep += linearize_amr_child
        if is_root:
            linearized_graph_rep += ")TOP-- "
        else:
            linearized_graph_rep += ")" + p_edge + _SPACE
        return linearized_graph_rep

    # level depth first amr linearization
    def level_linearize_amr_graph(self, cur_node, p_edge, is_root, level, sent_num):
        if level == 0:
            return _BLANK

        linearized_graph_rep = ''
        if is_root:
            linearized_graph_rep += "SENT" + str(sent_num) + "( " + global_info.node_labels[cur_node] + _SPACE
        else:
            linearized_graph_rep += p_edge + "( " + global_info.node_labels[cur_node] + _SPACE
        for neighbour in self.graph[cur_node].adjacency_list:
            linearize_amr_child = self.level_linearize_amr_graph(neighbour[0], neighbour[1], False, level-1, sent_num)
            linearized_graph_rep += linearize_amr_child
        if is_root:
            linearized_graph_rep += ")SENT" + str(sent_num) + _SPACE
        else:
            linearized_graph_rep += ")" + p_edge + _SPACE
        return linearized_graph_rep

    def get_linear_summary(self, _depth):
        for sent_num, root in enumerate(self.roots):
            linear_out = self.level_linearize_amr_graph(root, _EMPTY, True, _depth, sent_num)
            linear_out = _SPACE.join(linear_out.split())
            print linear_out
        return        


def buildCorpusAndWriteToFile(body_file, summ_file, w_exp, output_file):
    """
    build corpus and write it to file
    """
    corpus = buildCorpus(body_file, summ_file, w_exp)
    total_s_nodes = 0
    total_s_edges = 0
    total_body_nodes = 0
    total_body_edges = 0

    with codecs.open(output_file, 'w', 'utf-8') as outfile:
        for inst in corpus:
            my_nodes, s_nodes, r_nodes = inst.nodes  # @UnusedVariable
            my_edges, s_edges = inst.edges
            curr_filename = inst.filename

            total_s_nodes += len(s_nodes)
            total_s_edges += len(s_edges)
            total_body_nodes += len(my_nodes)
            total_body_edges += len(my_edges)

            outfile.write('%s\n' % curr_filename)
            for k_node, v_node in my_nodes.iteritems():
                tag = 0
                if k_node in s_nodes:
                    tag = 1
                outfile.write('%d %s %s\n' % (tag, k_node, v_node))


            for k_edge, v_edge in my_edges.iteritems():
                tag = 0
                if k_edge in s_edges:
                    tag = 1
                outfile.write('%d %s %s\n' % (tag, k_edge, v_edge))

            tGraph = TextGraph()
            tGraph.createGraph(my_edges, inst.nodes)
            text_graph_dict[curr_filename] = tGraph

    return


# utility function to separate out the data from amr file for textsum
def genTextSumFormatData(body_file, summ_file, suffix_str):

    logger.debug('building corpus [body file]: %s' % body_file)
    logger.debug('building corpus [summ file]: %s' % summ_file)
    body_corpus = loadFile(body_file)
    summ_corpus = loadFile(summ_file)
    corpus_dict = {}

    # append sentence
    for curr_filename in body_corpus:
        corpus_dict[curr_filename] = CorpusNode()
        doc_roots = body_corpus[curr_filename][1]
        for x in doc_roots:
            sources = doc_roots[x].sources
            for i in xrange(len(sources)):
                corpus_dict[curr_filename].appendSentenceText(sources[i].sentence)
                corpus_dict[curr_filename].appendSentenceAmr(sources[i].amr_str)

    # append summ
    for curr_filename in summ_corpus:
        if curr_filename in corpus_dict:
            doc_roots = summ_corpus[curr_filename][1]
            for x in doc_roots:
                sources = doc_roots[x].sources
                for i in xrange(len(sources)):
                    corpus_dict[curr_filename].appendSummText(sources[i].sentence)
                    corpus_dict[curr_filename].appendSummAmr(sources[i].amr_str)

    import pickle
    filehandler = open("amr_meta_data" + suffix_str + ".pkl","wb")
    pickle.dump(corpus_dict,filehandler)
    filehandler.close()



def buildCorpus(body_file, summ_file, w_exp=False):
    """
    build corpus from body and summary files
    """
    logger.debug('building corpus [body file]: %s' % body_file)
    logger.debug('building corpus [summ file]: %s' % summ_file)

    corpus = []
    body_corpus = loadFile(body_file)
    summ_corpus = loadFile(summ_file)

    for curr_filename in body_corpus:
        # sanity check
        if curr_filename not in summ_corpus:
            logger.error('[no summary sentences]: %s' % curr_filename)
            continue

        # nodes: (concept,) -> AmrNode
        # root_nodes: (concept,) -> AmrNode
        # edges: (concept1, concept2) -> AmrEdge
        # exp_edges: (concept1, concept2) -> AmrEdge
        body_nodes, body_root_nodes, body_edges, body_exp_edges = body_corpus[curr_filename]
        summ_nodes, _, summ_edges, _ = summ_corpus[curr_filename]
        num_summ_nodes = len(summ_nodes)
        num_summ_edges = len(summ_edges)

        # node_idx = 0
        node_indices = {}

        my_nodes = {}    # my_nodes: (1,) -> AmrNode
        s_nodes = set() # s_nodes: (1,), (3,), ...
        r_nodes = set() # r_ndoes: (1,), (2,), ...

        for anchor, node in body_nodes.iteritems():
            local_idx = 0
            if anchor[0] in global_info.inverse_node_labels:
                local_idx = global_info.inverse_node_labels[anchor[0]]
            else :
                global_info.node_idx += 1
                local_idx = global_info.node_idx
                global_info.node_labels[local_idx] = anchor[0]
                global_info.inverse_node_labels[anchor[0]] = local_idx

            my_nodes[(local_idx,)] = node
            node_indices[anchor[0]] = local_idx
            # node is selected if concept appears in summary
            # node is root node if it appears as root of ANY sentence
            if anchor in summ_nodes: s_nodes.add((local_idx,))
            if anchor in body_root_nodes: r_nodes.add((local_idx,))

        my_edges = {}    # my_edges: (1,2) -> AmrEdge
        s_edges = set() # s_edges: (1,2), (3,5), ...

        w_exp = False

        if w_exp: # with edge expansion
            for anchor, edge in body_exp_edges.iteritems():
                idx1 = node_indices[anchor[0]]
                idx2 = node_indices[anchor[1]]
                my_edges[(idx1, idx2)] = edge
                global_info.edge_relations.add(edge.relation)
                # edge is selected if concept pair appears in summary
                if anchor in summ_edges: s_edges.add((idx1, idx2))

        else: # without edge expansion
            for anchor, edge in body_edges.iteritems():
                idx1 = node_indices[anchor[0]]
                idx2 = node_indices[anchor[1]]
                my_edges[(idx1, idx2)] = edge
                if edge.relation in global_info.edge_relations:
                    global_info.edge_relations[edge.relation] += 1
                else:
                    global_info.edge_relations[edge.relation] = 1

                if anchor in summ_edges: s_edges.add((idx1, idx2))
#             for anchor, edge in body_exp_edges.iteritems():
#                 idx1 = node_indices[anchor[0]]
#                 idx2 = node_indices[anchor[1]]
#                 # edge is selected if concept pair appears in summary
#                 # selected edges are the same with or without edge expansion
#                 if anchor in summ_edges: s_edges.add((idx1, idx2))

        inst = Instance(curr_filename, (my_nodes, s_nodes, r_nodes), (my_edges, s_edges),
                        (num_summ_nodes, num_summ_edges))
        corpus.append(inst)

    # return list of Instances
    return corpus


def loadFile(input_filename):
    """
    load AMR parsed file, re-index AMR nodes and edges.
    return corpus of nodes and edges
    """
    graph_str = ''  # AMR parse
    graph_str_aligned = [] # Aligned graph str parts
    info_dict = {}  # AMR meta info

    doc_filename = ''
    corpus = {}     # filename -> (nodes, root_nodes, edges, exp_edges)

    doc_nodes = {}  # (concept,) -> AmrNode
    doc_root_nodes = {}  # (concept,) -> AmrNode
    doc_edges = {}  # (concept1, concept2) -> AmrEdge
    doc_exp_edges = {} # (concept1, concept2) -> AmrEdge

    with codecs.open(input_filename, 'r', 'utf-8') as infile:
        for line in infile:
            line = line.rstrip()
            if line == '':
                # no AMR graph for current sentence
                if graph_str == '':
                    info_dict = {}
                    continue
                # get nodes and edges (linked)
                g = AmrGraph()
                nodes, edges = g.getCollapsedNodesAndEdges(graph_str.split())

                # print graph_str_aligned.lstrip()

                # index nodes by graph_idx
                node_indices = {}
                for node in nodes:
                    graph_idx = node.graph_idx
                    node_indices.setdefault(graph_idx, node)

                # (1) use gold AMR annotation as input
                if not 'alignments' in info_dict:
                    # get sentence info
                    sentence = info_dict['snt'] # tokenized sentence
                    filename, line_num = info_dict['id'].split('.')
                    line_num = int(line_num)

                    # add source info to nodes
                    for node in nodes:
                        node_source = NodeSource(node.graph_idx, 0, 0, '', filename, line_num, sentence, graph_str_aligned)
                        node.sources.append(node_source)

                    # add source info to edges
                    for edge in edges:
                        edge_source = EdgeSource(edge.relation, filename, line_num, sentence)
                        edge.sources.append(edge_source)

                else: # (2) use alignment file as input

                    # get sentence info
                    sentence = info_dict['tok'] # tokenized sentence
                    tokens = sentence.split()
                    if len(info_dict['id'].split('.')) > 2:
                        continue

                    filename, line_num = info_dict['id'].split('.')
                    line_num = int(line_num)

                    # add source info to edges
                    for edge in edges:
                        edge_source = EdgeSource(edge.relation, filename, line_num, sentence)
                        edge.sources.append(edge_source)

                    # add alignment and other source info to nodes
                    alignments_str = info_dict['alignments']

                    for alignment in alignments_str.split():
                        word_part, graph_part = alignment.split('|')
                        start_idx, end_idx = map(int, word_part.split('-'))
                        graph_indices = graph_part.split('+')

                        for graph_idx in graph_indices:
                            curr_node = node_indices.get(graph_idx, None)
                            if curr_node is None: continue

                            # add node source info
                            new_start_idx = start_idx
                            new_end_idx = end_idx
                            # change existing start_idx/end_idx to broadest coverage
                            if curr_node.sources:
                                curr_node_source = curr_node.sources.pop()
                                if new_start_idx > curr_node_source.start_idx:
                                    new_start_idx = curr_node_source.start_idx
                                if new_end_idx < curr_node_source.end_idx:
                                    new_end_idx = curr_node_source.end_idx
                            # update new node source
                            new_node_source = NodeSource(curr_node.graph_idx, new_start_idx, new_end_idx,
                                                         ' '.join(tokens[new_start_idx:new_end_idx]),
                                                         filename, line_num, sentence, graph_str_aligned)
                            curr_node.sources.append(new_node_source)

                    # add source info to [unaligned] nodes
                    for node in nodes:
                        if node.sources: continue
                        node_source = NodeSource(node.graph_idx, 0, 0, '', filename, line_num, sentence, graph_str_aligned)
                        node.sources.append(node_source)

                # start of new file
                if filename != doc_filename:
                    if doc_filename != '':
                        corpus[doc_filename] = (doc_nodes, doc_root_nodes, doc_edges, doc_exp_edges)
                    doc_filename = filename
                    doc_nodes = {}
                    doc_root_nodes = {}
                    doc_edges = {}
                    doc_exp_edges = {}

                # keep track of redirected nodes
                redirect_dict = {}

                # merge nodes
                first_node = True
                skip_merge = True

                # for getting the root nodes and skip merging of nodes
                if not skip_merge:
                    for node in nodes:
                        curr_anchor = tuple((node.concept,)) # tricky
                        if first_node == True:
                            doc_root_nodes[curr_anchor] = node
                            first_node = False

                if skip_merge:
                    for node in nodes:
                        curr_anchor = tuple((node.concept,)) # tricky
                        if curr_anchor in doc_nodes:
                            old_node = doc_nodes[curr_anchor]
                            old_node.sources.extend(node.sources)
                            redirect_dict[node] = old_node
                        else:
                            doc_nodes[curr_anchor] = node
                        # root node of sentence
                        if first_node == True:
                            doc_root_nodes[curr_anchor] = doc_nodes[curr_anchor]
                            first_node = False

                    # merge edges
                    edge_indices = {} # index edge by concepts
                    for edge in edges:

                        # update node linkage
                        if edge.node1 in redirect_dict:
                            edge.node1 = redirect_dict[edge.node1]
                        if edge.node2 in redirect_dict:
                            edge.node2 = redirect_dict[edge.node2]

                        curr_anchor = tuple((edge.node1.concept, edge.node2.concept)) # ignore relation
                        edge_indices[curr_anchor] = edge

                        if curr_anchor in doc_edges:
                            old_edge = doc_edges[curr_anchor]
                            old_edge.sources.extend(edge.sources)
                        else:
                            doc_edges[curr_anchor] = edge

                    # expand edges, nodes in each sentence are fully connected
                    for node1 in nodes:
                        for node2 in nodes:
                            curr_anchor = tuple((node1.concept, node2.concept))
                            redirect_node1 = doc_nodes[(node1.concept,)]
                            redirect_node2 = doc_nodes[(node2.concept,)]

                            # expanded edge exists
                            if curr_anchor in doc_exp_edges:
                                # update node linkage
                                old_edge = doc_exp_edges[curr_anchor]
                                old_edge.node1 = redirect_node1
                                old_edge.node2 = redirect_node2
                                # update edge sources
                                if curr_anchor in edge_indices: # true edge
                                    edge = edge_indices[curr_anchor]
                                    old_edge.sources.extend(edge.sources)
                                else: # NULL edge
                                    edge_source = EdgeSource('NULL', filename, line_num, sentence)
                                    old_edge.sources.append(edge_source)

                            else: # expanded edge does not exist, build a new edge
                                if curr_anchor in edge_indices: # true edge
                                    edge = edge_indices[curr_anchor]
                                    new_edge = AmrEdge(node1=redirect_node1, node2=redirect_node2, relation=edge.relation)
                                    new_edge.sources.extend(edge.sources)
                                else: # NULL edge
                                    new_edge = AmrEdge(node1=redirect_node1, node2=redirect_node2, relation='NULL')
                                    edge_source = EdgeSource('NULL', filename, line_num, sentence)
                                    new_edge.sources.append(edge_source)
                                doc_exp_edges[curr_anchor] = new_edge

                # clear cache
                graph_str = ''
                graph_str_aligned = []
                info_dict = {}
                continue

            if line.startswith('#'):
                fields = line.split('::')
                for field in fields[1:]:
                    tokens = field.split()
                    info_name = tokens[0]
                    info_body = ' '.join(tokens[1:])
                    info_dict[info_name] = info_body
                continue

            graph_str += line
            graph_str_aligned.append(line)

    # add nodes and edges to the last file
    corpus[doc_filename] = (doc_nodes, doc_root_nodes, doc_edges, doc_exp_edges)
    return corpus

def print_graph_stats():
    print "printing graph stats ::"
    print "distinct node count ::", len(global_info.node_labels)
    print "distinct edge labels ::", len(global_info.edge_relations)
    print "disctinct filtered edge relations ::", len(global_info.get_attribute_dict())
    print "number of graphs ::", len(text_graph_dict)

if __name__ == '__main__':

    ap = argparse.ArgumentParser()
    ap.add_argument("-d", "--depth", help="depth of graph to traverse")
    args = vars(ap.parse_args())

    # input_dir = '/Users/user/Data/SemanticSumm/Proxy/gold/split/dev'

    # body_file = 'aligned-amr-release-1.0-dev-proxy-body.txt'
    # summ_file = 'aligned-amr-release-1.0-dev-proxy-summary.txt'
    input_dir = '/Users/amit/Desktop/Thesis/jamr/biocorpus/amr_parsing/data/amr-release-1.0-dev-proxy'
    body_file = 'test.txt'
    summ_file = 'alignedsum.txt'

    # input_dir = '/Users/amit/Desktop/Thesis/jamr/biocorpus/amr_parsing/data/jamr/dev'
    # body_file = 'amr-release-1.0-cleaned-proxy.aligned'
    # summ_file = 'amr-release-1.0-cleanessd-summary.aligned'

    _depth = int(args["depth"])
    suffix_str = "dev"
    # genTextSumFormatData(os.path.join(input_dir, body_file),
    #                      os.path.join(input_dir, summ_file), suffix_str)

    # if _depth:
    #     exit(0)

    buildCorpusAndWriteToFile(os.path.join(input_dir, body_file),
                              os.path.join(input_dir, summ_file),
                              w_exp=True, output_file='output_file')

    print_graph_stats()

    # print "nodes info ----------------------------------------------------------------------------"
    # for k in global_info.node_labels:
        # print k, global_info.node_labels[k]
    # print "node info ends -------------------------------------------------------------------------"

    # print "edge info ------------------------------------------------------------------------------"
    # for k in sorted(global_info.edge_relations):
        # print k
    # print "edge info ends -------------------------------------------------------------------------"

    linearized_graph_dict = {}

    with codecs.open("linearized_graph_rep", 'w', 'utf-8') as outfile:
        for filename in text_graph_dict:
            # linearized_graph_dict[filename] = text_graph_dict[filename].linearize_level_ordered(_depth)
            # print linearized_graph_dict[filename]
            text_graph_dict[filename].linearize_amr_graphs()
            text_graph_dict[filename].get_linear_summary(_depth)
            # outfile.write("%s\n" % filename)
            # outfile.write("%s\n" % linearized_graph_dict[filename])

    # linear_file = open("linear_sent.pkl","wb")
    # pickle.dump(linearized_graph_dict, linear_file)
    # linear_file.close()
