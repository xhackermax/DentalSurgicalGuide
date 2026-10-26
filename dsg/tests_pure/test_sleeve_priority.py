import unittest
from types import SimpleNamespace
from dsg.sleeve_priority import select_sleeve_routes

def route(label,origin,port,length,points=None):
    return SimpleNamespace(route_id=label,start_id=origin,end_id=port,length_mm=length,points_mm=points or ((0.,0.,0.),(length,0.,0.)))

class SleevePriorityTests(unittest.TestCase):
    def test_longer_alternative_recovers_three_supports(self):
        routes=[route('Ashort','A','P0',1),route('Along','A','P0',4),route('B','B','P0',2),route('C','C','P0',2)]
        incompatible={frozenset(('Ashort','B')),frozenset(('Ashort','C'))}
        chosen,report=select_sleeve_routes(routes,{r.route_id:'S1' for r in routes},lambda a,b:frozenset((a.route_id,b.route_id)) not in incompatible)
        self.assertEqual({r.route_id for r in chosen},{'Along','B','C'})
        self.assertTrue(report['search_complete']);self.assertEqual(report['direct_connection_count'],3)

    def test_port_diversity_precedes_shorter_length(self):
        routes=[route('A','A','P0',1),route('Bshort','B','P0',1),route('Bdiverse','B','P1',5)]
        chosen,report=select_sleeve_routes(routes,{r.route_id:'S1' for r in routes},lambda a,b:True)
        self.assertEqual({r.route_id for r in chosen},{'A','Bdiverse'})
        self.assertEqual(report['distinct_sleeve_port_count'],2)

    def test_global_cross_sleeve_compatibility(self):
        routes=[route('A','A','P0',1),route('B','B','P1',1)]
        chosen,report=select_sleeve_routes(routes,{'A':'S1','B':'S2'},lambda a,b:False)
        self.assertEqual(len(chosen),1);self.assertTrue(report['search_complete'])

    def test_deduplication_and_input_order_are_deterministic(self):
        routes=[route('z','A','P0',1),route('a','A','P0',1),route('B','B','P1',2)]
        results=[]
        for values in (routes,list(reversed(routes))):
            chosen,report=select_sleeve_routes(values,{r.route_id:'S1' for r in routes},lambda a,b:True)
            results.append(tuple(r.route_id for r in chosen));self.assertEqual(report['deduplicated_candidate_count'],2)
        self.assertEqual(results[0],results[1]);self.assertIn('a',results[0])

    def test_budget_exhaustion_is_truthful(self):
        routes=[route(str(i),str(i),'P0',1) for i in range(5)]
        chosen,report=select_sleeve_routes(routes,{r.route_id:'S1' for r in routes},lambda a,b:True,budget=2)
        self.assertFalse(report['search_complete']);self.assertFalse(report['maximum_direct_connections_proven'])
        self.assertEqual(report['search_states_visited'],2)
        self.assertEqual(report['search_budget'],2)

    def test_coverage_precedes_port_diversity(self):
        routes=[route('A','A','P0',1),route('B','B','P0',1),route('C','C','P0',1),route('D','D','P1',1)]
        chosen,report=select_sleeve_routes(routes,{r.route_id:'S1' for r in routes},lambda a,b:'D' not in (a.route_id,b.route_id))
        self.assertEqual({r.route_id for r in chosen},{'A','B','C'})
        self.assertEqual(report['supported_origins_by_sleeve'],{'S1':['A','B','C']})

    def test_shortest_length_breaks_equal_coverage_and_ports(self):
        routes=[route('Ashort','A','P0',1),route('Along','A','P0',3),route('B','B','P1',2)]
        chosen,_=select_sleeve_routes(routes,{r.route_id:'S1' for r in routes},lambda a,b:True)
        self.assertEqual({r.route_id for r in chosen},{'Ashort','B'})

    def test_one_route_per_sleeve_origin_but_cross_sleeve_origin_can_repeat(self):
        routes=[route('A','P1','PORT0',1),route('B','P1','PORT1',2),route('C','P1','PORT0',3)]
        chosen,report=select_sleeve_routes(routes,{'A':'S1','B':'S1','C':'S2'},lambda a,b:True)
        self.assertEqual({r.route_id for r in chosen},{'A','C'})
        self.assertEqual(report['supported_origins_by_sleeve'],{'S1':['P1'],'S2':['P1']})

    def test_empty_pool_is_proven_complete(self):
        chosen,report=select_sleeve_routes((),{},lambda a,b:True)
        self.assertEqual(chosen,());self.assertTrue(report['search_complete'])

    def test_minimum_per_sleeve_precedes_global_port_diversity(self):
        routes=[route('A','A','P0',1),route('B','B','P1',1),route('C','C','P2',1),route('D','D','P0',1),route('E','E','P0',1)]
        owners={r.route_id:('S1' if r.route_id in 'ABC' else 'S2') for r in routes}
        compatible=lambda a,b:{a.route_id,b.route_id}!={'C','E'}
        unrestricted,_=select_sleeve_routes(routes,owners,compatible)
        self.assertEqual({r.route_id for r in unrestricted},{'A','B','C','D'})
        chosen,report=select_sleeve_routes(routes,owners,compatible,minimum_per_sleeve=2)
        self.assertEqual({r.route_id for r in chosen},{'A','B','D','E'})
        self.assertTrue(report['minimum_connections_satisfied']);self.assertEqual(report['minimum_per_sleeve'],2)

    def test_unsatisfiable_minimum_returns_no_feasible_set(self):
        routes=[route('A','A','P0',1)]
        chosen,report=select_sleeve_routes(routes,{'A':'S1'},lambda a,b:True,minimum_per_sleeve=2)
        self.assertEqual(chosen,());self.assertEqual(report['direct_connection_count'],0)
        self.assertFalse(report['minimum_connections_satisfied']);self.assertTrue(report['search_complete'])
        self.assertFalse(report['maximum_direct_connections_proven'])

    def test_alternatives_retain_diverse_two_branch_fallback(self):
        routes=[route('A','A','P0',1),route('B','B','P0',1),route('C','C','P0',1),route('D','D','P1',1)]
        owners={r.route_id:'S1' for r in routes}
        compatible=lambda a,b:'D' not in {a.route_id,b.route_id} or 'C' not in {a.route_id,b.route_id}
        chosen,report=select_sleeve_routes(routes,owners,compatible,minimum_per_sleeve=2,alternatives_limit=3)
        self.assertEqual(len(chosen),3)
        alternatives=[set(ids) for ids in report['alternative_route_sets']]
        self.assertIn({r.route_id for r in chosen},alternatives)
        self.assertTrue(any(len(ids)==2 and 'D' in ids for ids in alternatives))
        self.assertEqual(len(alternatives),3)

    def test_alternatives_rank_coverage_then_ports_then_length(self):
        routes=[route('A','A','P0',1),route('B','B','P1',1),route('C','C','P0',1)]
        _,report=select_sleeve_routes(routes,{r.route_id:'S1' for r in routes},lambda a,b:True,minimum_per_sleeve=2)
        self.assertEqual(report['alternative_route_sets'],[['A','B','C'],['A','B'],['B','C'],['A','C']])
        self.assertTrue(report['alternatives_complete'])

if __name__=='__main__':unittest.main()
