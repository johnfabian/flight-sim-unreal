#include "CoastalScene.h"
#include "Components/SplineComponent.h"
#include "Engine/World.h"
#include "CollisionQueryParams.h"
ACoastalScene::ACoastalScene() {
    Tour=CreateDefaultSubobject<USplineComponent>(TEXT("GuidedFlyover")); SetRootComponent(Tour);
}
float ACoastalScene::GroundHeight(FVector Point) const {
    FHitResult Hit; FCollisionQueryParams Query(SCENE_QUERY_STAT(CoastalGround),true,this);
    const bool Found=GetWorld()->LineTraceSingleByChannel(Hit,FVector(Point.X,Point.Y,100000),FVector(Point.X,Point.Y,-10000),ECC_WorldStatic,Query);
    return Found?FMath::Max(0.f,float(Hit.ImpactPoint.Z)):0.f;
}
bool ACoastalScene::ValidateTour(float MinimumClearance) const {
    const double Length=Tour->GetSplineLength();
    if(Tour->GetNumberOfSplinePoints()<3 || !FMath::IsFinite(Length) || Length<=0 || !FMath::IsFinite(TourDuration) || TourDuration<=0 || !FMath::IsFinite(MinimumClearance) || MinimumClearance<0) return false;
    // Maximum ten metres between samples, independent of route length. Reject
    // unreasonable routes instead of silently stretching the sampling interval.
    const double Required=FMath::CeilToDouble(Length/1000.0);
    if(Required>20000) return false;
    const int32 Samples=FMath::Max(1,int32(Required));
    FVector Previous=Tour->GetLocationAtDistanceAlongSpline(0,ESplineCoordinateSpace::World);
    FCollisionQueryParams Query(SCENE_QUERY_STAT(CoastalTour),true,this);
    for(int J=0;J<=Samples;++J) {
        const FVector P=Tour->GetLocationAtDistanceAlongSpline(Length*J/Samples,ESplineCoordinateSpace::World);
        if(!WithinBounds(P) || P.Z-GroundHeight(P)<MinimumClearance) return false;
        FHitResult Hit;
        if(J>0 && GetWorld()->SweepSingleByChannel(Hit,Previous,P,FQuat::Identity,ECC_WorldStatic,FCollisionShape::MakeSphere(FMath::Max(1.f,MinimumClearance)),Query)) return false;
        Previous=P;
    }
    return true;
}
bool ACoastalScene::WithinBounds(FVector P) const {
    return !P.ContainsNaN() && P.Z>=180 && P.Z<=FlightBounds.Z && FMath::Abs(P.X)<=FlightBounds.X && FMath::Abs(P.Y)<=FlightBounds.Y;
}
bool ACoastalScene::Collides(const FlightSim::State& Before,const FlightSim::State& After,const AActor* Ignored) const {
    const FVector A=ToWorld(Before.position),B=ToWorld(After.position);
    if(!WithinBounds(B)) return true;
    const FQuat Rotation=FRotator(FMath::RadiansToDegrees(After.pitch),-FMath::RadiansToDegrees(After.heading),-FMath::RadiansToDegrees(After.roll)).Quaternion();
    FCollisionQueryParams Query(SCENE_QUERY_STAT(CoastalAircraft),false,Ignored);
    FHitResult Hit;
    // Two swept proxies cover the fuselage and wings, including near-horizontal cliffs.
    if(GetWorld()->SweepSingleByChannel(Hit,A,B,Rotation,ECC_WorldStatic,FCollisionShape::MakeBox(FVector(330,60,80)),Query)) {
        if(FMath::IsNearlyZero(FVector::DistSquared(A,AirborneSpawn)) && A==B)
            UE_LOG(LogTemp,Display,TEXT("AERONAUT_SPAWN_HIT %s at %s ground=%.1f"),*GetNameSafe(Hit.GetActor()),*B.ToString(),GroundHeight(B));
        return true;
    }
    const FVector WingOffset=Rotation.RotateVector(FVector(0,0,135));
    return GetWorld()->SweepSingleByChannel(Hit,A+WingOffset,B+WingOffset,Rotation,ECC_WorldStatic,FCollisionShape::MakeBox(FVector(65,550,14)),Query);
}
