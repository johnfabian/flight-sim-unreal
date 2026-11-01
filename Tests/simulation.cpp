#include "../Source/Aeronaut/FlightSimulation.h"
#include <cassert>
#include <iostream>
using namespace FlightSim;
int main() {
    State s;
    Step(s,{},.05); assert(s.elapsed==0);
    s.status=Status::Flying;
    for(int i=0;i<1200;++i) Step(s,{},1.0/60);
    assert(s.checkpoint==1 && s.score>990 && s.status==Status::Flying);
    State right; right.status=Status::Flying;
    for(int i=0;i<180;++i) Step(right,{0,1,0,0},1.0/60);
    assert(right.position.x>0 && right.roll<0);
    State climb; climb.status=Status::Flying;
    for(int i=0;i<180;++i) Step(climb,{1,0,0,1},1.0/60);
    assert(climb.position.y>300 && climb.throttle<=1);
    State crash; crash.status=Status::Flying; crash.position={0,1,380}; Step(crash,{},.01); assert(crash.status==Status::Crashed);
    State stall; stall.status=Status::Flying; stall.speed=26; stall.throttle=0; Step(stall,{},.05); assert(stall.stall && stall.verticalSpeed<0);
    State paused; paused.status=Status::Paused; Step(paused,{1,1,1,1},.05); assert(paused.elapsed==0 && paused.throttle==.68);
    State free; free.status=Status::Flying; free.freeFlight=true; free.position={0,280,-899}; Step(free,{},.05); assert(free.checkpoint==0);
    State missed; missed.status=Status::Flying; missed.position={200,280,-899}; Step(missed,{},.05); assert(missed.checkpoint==0);
    State front; front.status=Status::Flying; front.position={0,280,-850}; Step(front,{},.05); assert(front.checkpoint==0);
    State backwards; backwards.status=Status::Flying; backwards.position={0,280,-901}; backwards.heading=3.141592653589793; Step(backwards,{},.05); assert(backwards.checkpoint==0);
    for(int i=0;i<8;++i) {
        State gate; gate.status=Status::Flying; gate.checkpoint=i;
        gate.position={Gates[i].x,Gates[i].y,Gates[i].z+1}; Step(gate,{},.05);
        assert(gate.checkpoint==i+1 && gate.score==1000);
        if(i==7) assert(gate.status==Status::Complete);
    }
    assert(std::abs(Terrain(-870,-70)-13)<1e-9);
    assert(Terrain(14000,17000)==-25);
    State a,b; a.status=b.status=Status::Flying;
    for(int i=0;i<600;++i) Step(a,{.1,.2,0,0},1.0/60);
    for(int i=0;i<1200;++i) Step(b,{.1,.2,0,0},1.0/120);
    assert(std::abs(a.position.x-b.position.x)<1);
    // An authored world supplies collision independently of the legacy island formula.
    State authored; authored.status=Status::Flying; authored.freeFlight=true; authored.position={-1400,30,-1800};
    int calls=0;
    Step(authored,{},.01,[&](const State& before,const State& after){++calls; assert(after.position.z<before.position.z); return false;});
    assert(calls==1 && authored.status==Status::Flying);
    Step(authored,{},.01,[](const State&,const State&){return true;});
    assert(authored.status==Status::Crashed);
    State pausedQuery; pausedQuery.status=Status::Paused;
    Step(pausedQuery,{},.01,[](const State&,const State&)->bool{assert(false);return true;});
    assert(pausedQuery.elapsed==0);
    std::cout << "PASS: idle, cruise gate, steering, climb, crash, stall, pause, free flight, missed/front/backward gates, all eight gates, terrain, frame rates\n";
}
