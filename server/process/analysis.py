import json
from collections import defaultdict

import networkx as nx
from networkx.readwrite import json_graph


def exploration(query, data):
    network = {}
    nodes = {}
    supernode = {}
    #initialize node sets of each type
    for t in data.meta['node'].keys():
        nodes[t] = set()
        if 'filters' in query and t in query['filters'].keys():
            for label in query['filters'][t]:
                nodes[t] |= set(data.labels[t][label])
        else:
            nodes[t] = set(data.nodes[t].keys())
        for n in nodes[t]:
            supernode[n] = n
        if 'merges' in query and t in query['merges'].keys():
            for label in query['merges'][t]:
                for n in data.labels[t][label]:
                    supernode[n] = 's/'+t+'/'+label

    #compute filters by intersection
    for t in nodes.keys():
        for link_t in data.meta['link'].keys():
            if data.meta['link'][link_t][0] == t and data.meta['link'][link_t][1] != t:
                tmp = set()
                for n in nodes[t]:
                    if n in data.links[link_t].keys():
                        tmp |= set(data.links[link_t][n].keys())
                nodes[data.meta['link'][link_t][1]] &= tmp

    #extract links
    links = defaultdict(int)
    node_size = defaultdict(int)
    for link_t in data.meta['link'].keys():
        if data.meta['link'][link_t][0] in query['nodes'] and data.meta['link'][link_t][1] in query['nodes']:
            for n1 in nodes[data.meta['link'][link_t][0]]:
                if n1 in data.links[link_t].keys():
                    n2set = set(data.links[link_t][n1].keys()) & nodes[data.meta['link'][link_t][1]]
                    node_size[supernode[n1]] += len(n2set)
                    for n2 in n2set:
                        links[supernode[n1]+'_'+supernode[n2]] += int(data.links[link_t][n1][n2])
                        #node_size[supernode[n2]] += 1

    #collect links
    network['links'] = []
    for k in links.keys():
        n1 = k.split('_')[0]
        n2 = k.split('_')[1]
        network['links'].append({'source': n1, 'target': n2, 'weight': links[k]})

    #collect nodes
    network['nodes'] = []
    for t in nodes.keys():
        if t in query['nodes']:
            sup = set()
            for n in nodes[t]:
                if supernode[n] == n:
                    network['nodes'].append({'id': n, 'type': data.meta['node'][t]['name'], 'name': data.nodes[t][n], 'size': node_size[n]})
                else:
                    sup.add(supernode[n])
            for n in sup:
                network['nodes'].append({'id': n, 'type': data.meta['node'][t]['name'], 'name': data.meta['label'][t][n.split('/')[2]][0], 'size': node_size[n]})

    return network

def properties(dim):
    NUM_PROPERTIES = 3
    from server.process.config import args
    meta = json.load(open(args['meta_json'], 'r'))
    query = json.load(open(args['query_json'], 'r'))
    from server.process.dataset import Dataset
    data = Dataset(args)

    # add the contrasted node type to the subnetworks
    if dim not in query['nodes']:
        query['nodes'].append(dim)

    # remove the contrasted node type from filters
    if dim in query['filters']:
        query['filters'].pop(dim)

    # initialize property list
    prop = [{} for i in range(NUM_PROPERTIES)]
    prop[0]['name'] = 'size'
    prop[1]['name'] = 'radius'
    prop[2]['name'] = 'density'
    prop[0]['labels'] = []
    prop[1]['labels'] = []
    prop[2]['labels'] = []

    for i in meta['label'][dim]:
        # retrieve network connected to the contrasted node
        query['filters'][dim] = [i]
        network = exploration(query, data)
        
        sub_graph = json_graph.node_link_graph(network)
        gen = nx.connected_component_subgraphs(sub_graph)

        if len(network['nodes']) > 0:
            connected_graph = max(gen, key=len)
            prop[0]['labels'].append({'name': meta['label'][dim][i][0], 'val': len(network['nodes'])})
            prop[1]['labels'].append({'name': meta['label'][dim][i][0], 'val': nx.radius(connected_graph)})
            prop[2]['labels'].append({'name': meta['label'][dim][i][0], 'val': nx.density(connected_graph)})
        else:
            prop[0]['labels'].append({'name': meta['label'][dim][i][0], 'val': 0})
            prop[1]['labels'].append({'name': meta['label'][dim][i][0], 'val': 0})
            prop[2]['labels'].append({'name': meta['label'][dim][i][0], 'val': 0})

        query['filters'].pop(dim)

    results = {}
    results['node_type'] = meta['node'][dim]['name']
    results['properties'] = prop

    return results

def patterns(dim):
    THRESH_POP = 0.3
    THRESH_DIS = 0.2
    THRESH_INT = 2

    from server.process.config import args
    meta = json.load(open(args['meta_json'], 'r'))
    query = json.load(open(args['query_json'], 'r'))
    from server.process.dataset import Dataset
    data = Dataset(args)

    # add the contrasted node type to the subnetworks
    if dim not in query['nodes']:
        query['nodes'].append(dim)

    # remove the contrasted node type from filters
    if dim in query['filters']:
        query['filters'].pop(dim)

    counts = defaultdict(dict)
    node_type = {}
    node_name = {}
    for i in meta['label'][dim]:
        # retrieve network connected to the contrasted node
        query['filters'][dim] = [i]
        query['merges'][dim] = [i]
        network = exploration(query, data)
        links = {}
        for link in network['links']:
            links[link['source']+'_'+link['target']] = link['weight']
        for node in network['nodes']:
            if node['id'] not in node_type:
                node_type[node['id']] = node['type']
                node_name[node['id']] = node['name']
            if (node['id']+'_s/'+dim+'/'+i) in links:
                counts[node['id']][i] = links[node['id']+'_s/'+dim+'/'+i]
                if 'total' in counts[node['id']]:
                    counts[node['id']]['total'] += links[node['id']+'_s/'+dim+'/'+i]
                else:
                    counts[node['id']]['total'] = links[node['id']+'_s/'+dim+'/'+i]

    networks = {}
    for i in meta['label'][dim]:
        networks[i] = {'nodes':[], 'links':[]}
        for node_id in counts.keys():
            if i in counts[node_id]:
                if counts[node_id]['total'] > THRESH_POP * len(meta['label'][dim]) \
                        and counts[node_id][i] > THRESH_DIS * counts[node_id]['total']:
                    networks[i]['nodes'].append({
                                                 'id': node_id,
                                                 'type': node_type[node_id],
                                                 'name': node_name[node_id],
                                                 'size': counts[node_id][i]})
        for node_1 in networks[i]['nodes']:
            for node_2 in networks[i]['nodes']:
                if node_1['id'] != node_2['id']:
                    if (node_1['id']+'_'+node_2['id']) in links or \
                            (i in counts[node_1['id']] and \
                            i in counts[node_2['id']] and \
                            counts[node_1['id']][i] > THRESH_INT and \
                            counts[node_2['id']][i] > THRESH_INT):
                        weight = min(counts[node_1['id']][i], counts[node_2['id']][i])
                        if (node_1['id']+'_'+node_2['id']) in links:
                            weight = max(links[node_1['id']+'_'+node_2['id']], weight)
                        networks[i]['links'].append({
                                                     'source': node_1['id'],
                                                     'target': node_2['id'],
                                                     'weight': weight})

    return(networks)

'''
def test(args):
    q0 = {"nodes": ["0", "1", "2", "3"], "filters": {"0": ["3"], "1": ["1"]}, "merges": {"2": ["0", "1"]}}
    q1 = {"nodes": ["0", "1", "2", "3"], "filters": {}, "evals": {"1": ["0", "1"]}}
    q2 = {"nodes": ["0", "1", "2", "3"], "filters": {"2": ["0"], "3": ["2", "3"]}, "evals": {"1": ["0", "1"]}}
    q3 = {"nodes": ["0", "1"], "filters": {"0": ["3"], "2": ["0"], "3": ["2", "3"]}}
    q4 = {"nodes": ["1"], "filters": {"2": ["0"], "3": ["2", "3"]}}
    q5 = {"nodes": ["1"], "filters": {"1": ["1"], "2": ["0"], "3": ["2", "3"]}}

    json.dump(q2, open(args['query_file'], 'w'))
    data = Dataset(args)
    analysis(data, args)

if __name__ == '__main__':
    test(args)
'''