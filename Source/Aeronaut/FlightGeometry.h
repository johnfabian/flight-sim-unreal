#pragma once
#include "CoreMinimal.h"
#include "ProceduralMeshComponent.h"
// Small, batched mesh builder: no downloaded assets, physics meshes or Nanite.
namespace FlightGeometry {
inline FVector Position(double X,double Y,double Z) { return FVector(-Z*100,X*100,Y*100); }
inline FLinearColor Color(const TCHAR* Hex) { return FLinearColor(FColor::FromHex(Hex)); }
struct Mesh {
    TArray<FVector> V,N;
    TArray<int32> I;
    TArray<FVector2D> UV;
    TArray<FLinearColor> C;
    void Tri(FVector A,FVector B,FVector D,FLinearColor Col) {
        const int32 Start=V.Num();
        // UE clockwise front face; this cross product points out of the surface.
        const FVector Normal=FVector::CrossProduct(D-A,B-A).GetSafeNormal();
        V.Append({A,B,D}); N.Append({Normal,Normal,Normal});
        I.Append({Start,Start+1,Start+2}); C.Append({Col,Col,Col});
        UV.Append({FVector2D(0,0),FVector2D(0,1),FVector2D(1,1)});
    }
    void Quad(FVector A,FVector B,FVector D,FVector E,FLinearColor Col) { Tri(A,B,D,Col); Tri(A,D,E,Col); }
    void Box(FVector P,FVector Size,FLinearColor Col) {
        const FVector H=Size*.5;
        const FVector A=P+FVector(-H.X,-H.Y,-H.Z), B=P+FVector(H.X,-H.Y,-H.Z), D=P+FVector(H.X,H.Y,-H.Z), E=P+FVector(-H.X,H.Y,-H.Z);
        const FVector F=P+FVector(-H.X,-H.Y,H.Z), G=P+FVector(H.X,-H.Y,H.Z), J=P+FVector(H.X,H.Y,H.Z), K=P+FVector(-H.X,H.Y,H.Z);
        Quad(F,K,J,G,Col); Quad(A,B,D,E,Col); Quad(A,F,G,B,Col); Quad(B,G,J,D,Col); Quad(D,J,K,E,Col); Quad(E,K,F,A,Col);
    }
    void Ellipsoid(FVector P,FVector Radius,FLinearColor Col,int Segments=12,int Rows=8) {
        const int First=N.Num();
        auto Point=[&](int U,int W) { const double A=2*PI*U/Segments,B=PI*W/Rows; return P+FVector(std::cos(A)*std::sin(B)*Radius.X,std::sin(A)*std::sin(B)*Radius.Y,std::cos(B)*Radius.Z); };
        for(int Y=0;Y<Rows;++Y) for(int X=0;X<Segments;++X) Quad(Point(X,Y),Point(X+1,Y),Point(X+1,Y+1),Point(X,Y+1),Col);
        for(int J=First;J<N.Num();++J) { const FVector D=V[J]-P; N[J]=FVector(D.X/(Radius.X*Radius.X),D.Y/(Radius.Y*Radius.Y),D.Z/(Radius.Z*Radius.Z)).GetSafeNormal(); }
    }
    void Strut(FVector A,FVector B,double Radius,FLinearColor Col) {
        const FVector Direction=(B-A).GetSafeNormal();
        const FVector Side=FVector::CrossProduct(Direction,FVector::UpVector).GetSafeNormal()*Radius;
        const FVector Up=FVector::CrossProduct(Direction,Side).GetSafeNormal()*Radius;
        Quad(A+Side+Up,A-Side+Up,B-Side+Up,B+Side+Up,Col);
        Quad(A-Side-Up,A+Side-Up,B+Side-Up,B-Side-Up,Col);
        Quad(A+Side-Up,A+Side+Up,B+Side+Up,B+Side-Up,Col);
        Quad(A-Side+Up,A-Side-Up,B-Side-Up,B-Side+Up,Col);
    }
    void Cone(FVector Base,double Radius,double Height,FLinearColor Col) {
        for(int J=0;J<6;++J) {
            const double A=J*PI/3,B=(J+1)*PI/3;
            Tri(Base+FVector(Radius*std::cos(A),Radius*std::sin(A),0),Base+FVector(0,0,Height),Base+FVector(Radius*std::cos(B),Radius*std::sin(B),0),Col);
        }
    }
    void Ring(double Radius,double Thickness,FLinearColor Col) {
        auto P=[&](int A,int B) { double U=A*2*PI/80,W=B*2*PI/6; return FVector(std::sin(W)*Thickness,std::cos(U)*(Radius+std::cos(W)*Thickness),std::sin(U)*(Radius+std::cos(W)*Thickness)); };
        for(int A=0;A<80;++A) for(int B=0;B<6;++B) Quad(P(A,B),P(A,B+1),P(A+1,B+1),P(A+1,B),Col);
    }
    void Apply(UProceduralMeshComponent* Component,UMaterialInterface* Material) {
        Component->CreateMeshSection_LinearColor(0,V,I,N,UV,C,TArray<FProcMeshTangent>(),false);
        Component->SetMaterial(0,Material);
        Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Component->SetCastShadow(false);
    }
};
}
