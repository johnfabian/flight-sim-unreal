#pragma once
// Engine-independent port of flight-sim-codex/src/simulation.ts.
// Metres and radians; original axes: X east, Y up, -Z north.
#include <algorithm>
#include <cmath>
#include <array>
#include <functional>
namespace FlightSim {
inline double Clamp(double v, double a, double b) { return std::max(a, std::min(b,v)); }
inline double Damp(double a,double b,double rate,double dt) { return a+(b-a)*(1-std::exp(-rate*dt)); }
struct Vec { double x=0,y=0,z=0; };
struct Island { double x,z,rx,rz,height; };
inline constexpr std::array<Island,6> Islands = {{{-1400,-1800,1650,2300,570},{2050,-3700,1850,2100,960},{-1100,-6600,2000,1700,780},{2800,-8200,1400,1800,560},{-3300,-4300,900,1400,410},{3700,700,1200,1700,500}}};
struct Gate { double x,y,z; const char* name; };
inline constexpr std::array<Gate,8> Gates = {{{0,280,-900,"Into the blue"},{80,340,-2000,"The channel"},{0,390,-3200,"Between giants"},{-180,440,-4500,"Northern passage"},{-200,790,-5700,"Climb to the clouds"},{700,690,-6800,"Over the ridge"},{1600,510,-7600,"The far islands"},{2200,380,-9200,"Edge of the world"}}};
inline constexpr double GateRadius=120;
inline double Terrain(double x,double z) {
    double h=-25;
    for(const auto& i:Islands) {
        const double dx=(x-i.x)/i.rx,dz=(z-i.z)/i.rz,a=std::atan2(dz,dx);
        const double r=std::hypot(dx,dz)*(1+.09*std::sin(a*5)+.05*std::cos(a*9));
        if(r<1) {
            const double detail=std::sin(x*.005+z*.003)*.17+std::cos(z*.009-x*.002)*.11+std::sin(x*.021+z*.013)*.035;
            h=std::max(h,std::pow(1-r,1.65)*i.height*(1+detail)-7);
        }
    }
    if(x>-1020 && x<-720 && z>-440 && z<290) {
        const double edge=std::min({x+1020,-720-x,z+440,290-z});
        h+=(13-h)*Clamp(edge/65,0,1);
    }
    return h;
}
enum class Status { Briefing,Flying,Paused,Crashed,Complete };
struct Input { double pitch=0,roll=0,yaw=0,throttle=0; };
struct State {
    Vec position{0,280,380},previous{0,280,380};
    double heading=0,pitch=0,roll=0,speed=67,throttle=.68,verticalSpeed=0,elapsed=0,distance=0;
    int checkpoint=0,score=0;
    Status status=Status::Briefing;
    bool freeFlight=false,stall=false;
};
using CollisionQuery=std::function<bool(const State&,const State&)>;
inline bool LegacyCollision(const State&,const State& s) {
    return s.position.y<std::max(0.0,Terrain(s.position.x,s.position.z))+3 || s.position.y>3600 || std::abs(s.position.x)>14500 || std::abs(s.position.z)>18000;
}
inline void Step(State& s,const Input& in,double delta,const CollisionQuery& Collision=LegacyCollision) {
    if(s.status!=Status::Flying) return;
    const State Before=s;
    const double dt=Clamp(delta,0,.05);
    s.previous=s.position;
    s.throttle=Clamp(s.throttle+in.throttle*dt*.28,0,1);
    s.roll=Damp(s.roll,-in.roll*1.05,2.6,dt);
    s.pitch=Damp(s.pitch,in.pitch*.47,1.7,dt);
    s.heading+=(std::sin(s.roll)*.48+in.yaw*.2)*dt;
    s.speed=Damp(s.speed,25+s.throttle*76-std::sin(s.pitch)*22,.25,dt);
    s.stall=s.speed<37;
    s.verticalSpeed=std::sin(s.pitch)*s.speed-(s.stall?(37-s.speed)*1.9:0);
    s.position.x-=std::sin(s.heading)*std::cos(s.pitch)*s.speed*dt;
    s.position.z-=std::cos(s.heading)*std::cos(s.pitch)*s.speed*dt;
    s.position.y+=s.verticalSpeed*dt;
    s.distance+=s.speed*dt; s.elapsed+=dt;
    if(Collision(Before,s)) { s.status=Status::Crashed; return; }
    if(!s.freeFlight && s.checkpoint<static_cast<int>(Gates.size())) {
        const auto& g=Gates[s.checkpoint];
        if(s.previous.z>=g.z && s.position.z<g.z) {
            const double f=(g.z-s.previous.z)/(s.position.z-s.previous.z);
            const double d=std::hypot(s.previous.x+(s.position.x-s.previous.x)*f-g.x,s.previous.y+(s.position.y-s.previous.y)*f-g.y);
            if(d<GateRadius) {
                s.score+=static_cast<int>(std::round(500+500*(1-d/GateRadius)));
                if(++s.checkpoint==static_cast<int>(Gates.size())) s.status=Status::Complete;
            }
        }
    }
}
}
