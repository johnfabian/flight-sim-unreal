#include "FlightGame.h"
#include "FlightGeometry.h"
#include "Engine/World.h"
#include "Engine/DirectionalLight.h"
#include "Engine/SkyLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Materials/MaterialInterface.h"
using namespace FlightGeometry;

void AFlightPawn::BuildWorld() {
    Surface=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Aeronaut/M_Surface.M_Surface"));
    auto Make=[&](const TCHAR* Name,Mesh& Geometry) {
        AActor* Actor=GetWorld()->SpawnActor<AActor>();
        auto* Component=NewObject<UProceduralMeshComponent>(Actor,FName(Name));
        Actor->SetRootComponent(Component); Actor->AddInstanceComponent(Component); Component->RegisterComponent();
        Geometry.Apply(Component,Surface); return Component;
    };
    Mesh Terrain;
    FRandomStream Random(811);
    for(const auto& Island:FlightSim::Islands) {
        const int Grid=128, Start=Terrain.V.Num();
        for(int X=0;X<=Grid;++X) for(int Z=0;Z<=Grid;++Z) {
            const double East=Island.x+(double(X)/Grid-.5)*Island.rx*2.25;
            const double North=Island.z+(double(Z)/Grid-.5)*Island.rz*2.25;
            const double H=FlightSim::Terrain(East,North);
            const double Dx=(FlightSim::Terrain(East+3,North)-FlightSim::Terrain(East-3,North))/6;
            const double Dz=(FlightSim::Terrain(East,North+3)-FlightSim::Terrain(East,North-3))/6;
            Terrain.V.Add(Position(East,H,North));
            Terrain.N.Add(FVector(Dz,-Dx,1).GetSafeNormal());
            Terrain.UV.Add(FVector2D(East*.001,North*.001));
            auto Blend=[](double H,double Low,double High) { return float(FlightSim::Clamp((H-Low)/(High-Low),0,1)); };
            FLinearColor Col=FMath::Lerp(Color(TEXT("E6D2A1")),Color(TEXT("7F9E60")),Blend(H,10,35));
            Col=FMath::Lerp(Col,Color(TEXT("3F7157")),Blend(H,60,260));
            Col=FMath::Lerp(Col,Color(TEXT("8E9B8B")),Blend(H,340,650));
            Col=FMath::Lerp(Col,Color(TEXT("E7E8D9")),Blend(H,700,900));
            Col*=float(.97+.035*std::sin(East*.018)*std::cos(North*.015)); Col.A=1;
            Terrain.C.Add(Col);
        }
        for(int X=0;X<Grid;++X) for(int Z=0;Z<Grid;++Z) {
            const int A=Start+X*(Grid+1)+Z,B=A+Grid+1,D=B+1,E=A+1;
            Terrain.I.Append({A,E,D,A,D,B});
        }
    }
    Make(TEXT("Islands"),Terrain);
    Mesh Ocean;
    Ocean.Quad(FVector(-3000000,-3000000,0),FVector(-3000000,3000000,0),FVector(3000000,3000000,0),FVector(3000000,-3000000,0),Color(TEXT("238E9F")));
    auto* Water=Make(TEXT("Ocean"),Ocean);
    if(auto* WaterMaterial=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Aeronaut/M_Ocean.M_Ocean"))) Water->SetMaterial(0,WaterMaterial);
    Mesh Trees;
    for(int J=0;J<6500;++J) {
        const auto& I=FlightSim::Islands[Random.RandRange(0,5)];
        const double X=I.x+Random.FRandRange(-.9,.9)*I.rx,Z=I.z+Random.FRandRange(-.9,.9)*I.rz,H=FlightSim::Terrain(X,Z);
        if(H<28 || H>490 || (X>-1080 && X<-660 && Z>-480 && Z<330)) continue;
        if(std::sin(X*.009)*std::cos(Z*.007)<-.25) continue;
        const float Radius=Random.FRandRange(350,650),Height=Random.FRandRange(1400,2600);
        const FVector Base=Position(X,H,Z);
        Trees.Box(Base+FVector(0,0,Height*.18),FVector(100,100,Height*.36),Color(TEXT("6B6550")));
        Trees.Cone(Base+FVector(0,0,Height*.18),Radius,Height*.72,Color(TEXT("315E48")));
        Trees.Cone(Base+FVector(0,0,Height*.47),Radius*.72,Height*.60,Color(TEXT("4C7850")));
    }
    Make(TEXT("Trees"),Trees);
    Mesh Clouds;
    for(int J=0;J<26;++J) {
        FVector P=Position(Random.FRandRange(-8000,8000),Random.FRandRange(1500,2600),Random.FRandRange(-14000,2000));
        for(int K=0;K<4;++K) Clouds.Ellipsoid(P+FVector(0,K*10000,Random.FRandRange(-1500,1500)),FVector(10000,16000,6500),Color(TEXT("F4F0E3")),10,6);
    }
    Make(TEXT("Clouds"),Clouds);
    Mesh Airfield;
    Airfield.Box(Position(-870,13.5,-70),FVector(54000,4500,80),Color(TEXT("505C5A")));
    for(int J=0;J<13;++J) Airfield.Box(Position(-870,14,-310+J*40),FVector(1800,200,12),Color(TEXT("F3E9D0")));
    Airfield.Box(Position(-960,25,-120),FVector(7000,6500,2400),Color(TEXT("B5B3A0")));
    Airfield.Box(Position(-945,35,75),FVector(1000,1000,4600),Color(TEXT("EEE6D3")));
    Airfield.Box(Position(-945,61,75),FVector(2200,2200,1200),Color(TEXT("35565B")));
    Make(TEXT("Airfield"),Airfield);
    for(int J=0;J<8;++J) {
        Mesh Ring; Ring.Ring(FlightSim::GateRadius*100,240,Color(TEXT("FFB569")));
        auto* R=Make(*FString::Printf(TEXT("Gate%d"),J),Ring);
        const auto& G=FlightSim::Gates[J]; R->SetWorldLocation(Position(G.x,G.y,G.z)); Rings.Add(R);
        if(auto* GateMaterial=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Aeronaut/M_Gate.M_Gate"))) R->SetMaterial(0,GateMaterial);
    }
    auto* Sun=GetWorld()->SpawnActor<ADirectionalLight>();
    auto* SunComponent=Cast<UDirectionalLightComponent>(Sun->GetLightComponent());
    SunComponent->SetMobility(EComponentMobility::Movable);
    Sun->SetActorRotation(FRotator(-32,-35,0));
    SunComponent->SetIntensity(8.f); SunComponent->SetLightColor(FLinearColor(1.f,.92f,.80f));
    SunComponent->SetAtmosphereSunLight(true);
    auto* Atmosphere=GetWorld()->SpawnActor<AActor>();
    auto* Sky=NewObject<USkyAtmosphereComponent>(Atmosphere);
    Atmosphere->SetRootComponent(Sky); Atmosphere->AddInstanceComponent(Sky); Sky->RegisterComponent();
    auto* Ambient=GetWorld()->SpawnActor<ASkyLight>();
    Ambient->GetLightComponent()->SetMobility(EComponentMobility::Movable);
    Ambient->GetLightComponent()->SetIntensity(.8f);
    Ambient->GetLightComponent()->RecaptureSky();
    auto* Fog=GetWorld()->SpawnActor<AExponentialHeightFog>();
    Fog->GetComponent()->SetFogDensity(.0015f);
    Fog->GetComponent()->SetFogHeightFalloff(.12f);
    Fog->GetComponent()->SetFogInscatteringColor(FLinearColor(.53f,.72f,.75f));
}

void AFlightPawn::BuildAircraft() {
    if(CoastalScene) { BuildRealisticAircraft(); return; }
    const auto Cream=Color(TEXT("F0E8D2")),Orange=AccentColor,Dark=Color(TEXT("283B3E"));
    Mesh Body;
    Body.Ellipsoid(FVector(0,0,0),FVector(440,108,100),Cream,16,10);
    Body.Ellipsoid(FVector(310,0,0),FVector(145,115,110),Orange);
    Body.Ellipsoid(FVector(60,0,90),FVector(185,94,85),Color(TEXT("345B68")));
    Body.Box(FVector(20,0,160),FVector(235,1750,22),Cream);
    for(int Side:{-1,1}) {
        Body.Strut(FVector(80,Side*95,-40),FVector(20,Side*580,145),12,Dark);
        Body.Strut(FVector(-80,Side*95,-40),FVector(-65,Side*580,145),9,Dark);
        Body.Box(FVector(20,Side*630,175),FVector(235,30,8),Dark);
        Body.Box(FVector(20,Side*812,160),FVector(236,140,26),Orange);
        Body.Box(FVector(-170,Side*90,0),FVector(410,12,16),Orange);
        Body.Box(FVector(100,Side*125,-150),FVector(20,24,180),Dark);
        Body.Ellipsoid(FVector(100,Side*170,-245),FVector(46,20,46),Dark);
        Body.Ellipsoid(FVector(20,Side*880,164),FVector(12,12,12),Side<0?Color(TEXT("EF593E")):Color(TEXT("8CF0B5")),8,6);
    }
    Body.Ellipsoid(FVector(-440,0,10),FVector(240,65,62),Cream);
    Body.Box(FVector(-620,0,50),FVector(145,560,16),Cream);
    Body.Box(FVector(-620,0,150),FVector(175,16,250),Orange);
    Body.Apply(Aircraft,Surface);
    Mesh Blades; Blades.Box(FVector::ZeroVector,FVector(12,470,19),Dark);
    Blades.Ellipsoid(FVector(12,0,0),FVector(60,34,34),Cream);
    Blades.Apply(Propeller,Surface); Propeller->SetRelativeLocation(FVector(465,0,0));
}
